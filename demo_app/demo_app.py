# Copyright 2024 Snowflake Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import io
import json
import logging
import os
import queue
import re
import sys
import threading
import uuid
import warnings

import requests
import streamlit as st
from dotenv import load_dotenv
from snowflake.snowpark import Session

from agent_gateway import Agent
from agent_gateway import TruAgent
from agent_gateway.tools import CortexAnalystTool, CortexSearchTool, PythonTool
from trulens.connectors.snowflake import SnowflakeConnector
from agent_gateway.tools.utils import parse_log_message

warnings.filterwarnings("ignore")
load_dotenv("../.env")
st.set_page_config(page_title="Snowflake Cortex Cube")

connection_parameters = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "role": os.getenv("SNOWFLAKE_ROLE"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA"),
}

os.environ["NEWS_API_TOKEN"] = os.getenv("NEWS_API_TOKEN")


class NewsTool:
    def __init__(self, token, limit) -> None:
        self.api_token = token
        self.limit = limit

    def news_search(self, news_query: str) -> str:
        news_request = f"""https://api.thenewsapi.com/v1/news/all?api_token={self.api_token}&search={news_query}&language=en&limit={self.limit}"""
        response = requests.get(news_request)
        json_response = json.loads(response.content)["data"]

        return str(json_response)


python_config = {
    "tool_description": "searches for relevant news based on user query",
    "output_description": "relevant articles",
    "python_func": NewsTool(token=os.getenv("NEWS_API_TOKEN"), limit=3).news_search,
}

if "prompt_history" not in st.session_state:
    st.session_state["prompt_history"] = {}

if "snowpark" not in st.session_state or st.session_state.snowpark is None or "conn" not in st.session_state or st.session_state.conn is None:
    st.session_state.snowpark = Session.builder.configs(connection_parameters).create()
    st.session_state.conn = SnowflakeConnector(**connection_parameters)

    topic_search_config = {
        "service_name": "TOPIC_SEARCH",
        "service_topic": "Support case topics",
        "data_description": "Quarterly analysis of support case topics, specifically focusing on the domain of Rider Experience for a specific calendar quarter.",
        "retrieval_columns": ["topic_summary", "topic", "domain", "quarter", "case_count"],
        "snowflake_connection": st.session_state.snowpark,
    }

    domain_search_config = {
        "service_name": "DOMAIN_SEARCH",
        "service_topic": "Overview of main pain points, overall health scores of various topics, notable trends in metrics, and recommendations for areas that need immediate attention. This information is part of a broader document that analyzes support domain health metrics, including case volumes, severity rates, response times, and overall health scores across different domains.",
        "data_description": "Detailed analysis of the Driver Operations, Rider Experience, Corporate and Fleet Accounts, Safety and Security, Driver Operations, Loyalty and Promotions and App Connectivity product domains in different calendar quarters.",
        "retrieval_columns": ["domain_summary", "domain", "quarter"],
        "snowflake_connection": st.session_state.snowpark,
    }

    case_search_config = {
        "service_name": "CASE_SEARCH",
        "service_topic": "Support ticket details",
        "data_description": "Details of Support tickets on Ride booking, Ride tracking, Rating and feedback, Driver safety, Login authentication, Ride Verification, Background Checks, Incident reporting, Event rides, Expense tracking, Subscription plans, Payment options, Driver matching, Earnings dashboard, Navigation routes, App performance, Notifications, Language support, Emergency Features, Reward program, Promo codes, Corporate rides, Fleet management and Driver Rating Dashboard",
        "retrieval_columns": ["ticket_body", "domain","feature","topic","quarter","ticket_id","severity"],
        "snowflake_connection": st.session_state.snowpark,
    }

    ride_analyst_config = {
        "semantic_model": "rides.yaml",
        "stage": "SEMANTIC_YAMLS",
        "service_topic": "Rides related metrics",
        "data_description": "a table with Rides providing a comprehensive summary of ride data, including ride ID, customer and driver information, quarter, timestamp, location, and ride cost allowing for easy analysis and reporting of ride-related activities.",
        "snowflake_connection": st.session_state.snowpark,
    }

    support_ticket_analyst_config = {
        "semantic_model": "support_tickets.yaml",
        "stage": "SEMANTIC_YAMLS",
        "service_topic": "Support tickets related metrics",
        "data_description": "a table with Support Tickets providing a comprehensive summary of support tickets, including customer id, ticket details, and key metrics such as possession time, life time, and health scores.",
        "snowflake_connection": st.session_state.snowpark,
    }

    # Tools Config
    st.session_state.topic_search = CortexSearchTool(**topic_search_config)
    st.session_state.domain_search = CortexSearchTool(**domain_search_config)
    st.session_state.case_search = CortexSearchTool(**case_search_config)
    st.session_state.ride_analyst = CortexAnalystTool(**ride_analyst_config)
    st.session_state.support_ticket_analyst = CortexAnalystTool(**support_ticket_analyst_config)
    st.session_state.news_search = PythonTool(**python_config)
    st.session_state.snowflake_tools = [
        st.session_state.topic_search,
        st.session_state.domain_search,
        st.session_state.case_search,
        st.session_state.ride_analyst,
        st.session_state.support_ticket_analyst,
        st.session_state.news_search,
    ]


if "agent" not in st.session_state:
    st.session_state.agent = Agent(snowflake_connection=st.session_state.snowpark, tools=st.session_state.snowflake_tools)
    #st.session_state.agent = TruAgent(app_name="trulens_orchestration_framework_streamlit",app_version="v0.1",trulens_snowflake_connection=st.session_state.conn,tools=st.session_state.snowflake_tools,snowflake_connection=st.session_state.snowpark)


def create_prompt(prompt_key: str):
    if prompt_key in st.session_state:
        prompt_record = dict(prompt=st.session_state[prompt_key], response="waiting")
        st.session_state["prompt_history"][str(uuid.uuid4())] = prompt_record


source_list = []


class StreamlitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_buffer = io.StringIO()
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def emit(self, record):
        msg = self.format(record)
        clean_msg = self.ansi_escape.sub("", msg)
        self.log_buffer.write(clean_msg + "\n")

    def get_logs(self):
        return self.log_buffer.getvalue()

    def clear_logs(self):
        self.log_area.empty()


def setup_logging():
    root_logger = logging.getLogger()
    handler = StreamlitLogHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    return handler


# Set up logging
if "logging_setup" not in st.session_state:
    st.session_state.logging_setup = setup_logging()


def run_acall(prompt, message_queue, agent):
    old_stdout = sys.stdout
    new_stdout = io.StringIO()
    sys.stdout = new_stdout
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the async call
    response = loop.run_until_complete(agent.acall(prompt))
    loop.close()

    # Restore stdout
    sys.stdout = old_stdout

    # Capture and send logs to the message queue
    output = new_stdout.getvalue()
    lines = output.split("\n")
    for line in lines:
        if line and "Running" in line and "tool" in line:
            # Extract and send the tool selection string
            tool_selection_string = extract_tool_name(line)
            message_queue.put({"tool_selection": tool_selection_string})
        elif line:
            logging.info(line)  # Log other messages
            message_queue.put(line)

    # Ensure the final output is correctly added to the queue
    message_queue.put({"output": response})


def process_message(prompt_id: str):
    prompt = st.session_state["prompt_history"][prompt_id].get("prompt")
    message_queue = queue.Queue()
    agent = st.session_state.agent
    log_container = st.empty()
    log_handler = setup_logging()

    def run_analysis():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(agent.acall(prompt))
        loop.close()
        message_queue.put({"output": response})

    thread = threading.Thread(target=run_analysis)
    thread.start()

    while True:
        try:
            response = message_queue.get(timeout=0.1)
            if isinstance(response, dict) and "output" in response:
                final_response = f"{response['output']}"
                st.session_state["prompt_history"][prompt_id]["response"] = (
                    final_response
                )
                log_container.code(parse_log_message(log_handler.get_logs()))
                log_container.empty()
                yield final_response
                break
            else:
                # Handle other logs
                pass
        except queue.Empty:
            log_output = parse_log_message(log_handler.get_logs())
            if log_output is not None:
                log_container.code(log_output)
            # with st.spinner("Awaiting Response..."):
            #     pass
    st.rerun()


def extract_tool_name(statement):
    start = statement.find("Running") + len("Running") + 1
    end = statement.find("tool")
    return statement[start:end].strip()


st.markdown(
    """
    <style>
        div[data-testid="stHeader"] > img, div[data-testid="stSidebarCollapsedControl"] > img {
            height: 2rem;
            width: auto;
        }
        div[data-testid="stHeader"], div[data-testid="stHeader"] > *,
        div[data-testid="stSidebarCollapsedControl"], div[data-testid="stSidebarCollapsedControl"] > * {
            display: flex;
            align-items: center;
        }
    </style>
""",
    unsafe_allow_html=True,
)

st.logo("SIT_logo_white.png")

st.markdown(
    "<h1>🧠 Snowflake Cortex<sup style='font-size:.8em;'>3</sup></h1>",
    unsafe_allow_html=True,
)
st.caption(
    "A Multi-Agent System with access to Cortex, Cortex Search, Cortex Analyst, and more."
)

for id in st.session_state.prompt_history:
    current_prompt = st.session_state.prompt_history.get(id)

    with st.chat_message("user"):
        st.write(current_prompt.get("prompt"))

    with st.chat_message("assistant"):
        if current_prompt.get("response") == "waiting":
            # Create containers for tool selection and response
            tool_info_container = st.empty()
            response_container = st.empty()

            # Start processing messages
            message_generator = process_message(prompt_id=id)

            # Use a spinner while processing
            with st.spinner("Awaiting Response..."):
                for response in message_generator:
                    if "Using" in response:
                        tool_info_container.markdown(f"**{response}**")
                    else:
                        # Clear tool info once final response is ready
                        tool_info_container.empty()
                        response_container.markdown(response)
        else:
            # Display the final response
            st.markdown(
                st.session_state["prompt_history"][id]["response"],
                unsafe_allow_html=True,
            )

st.chat_input(
    "Ask Anything", on_submit=create_prompt, key="chat_input", args=["chat_input"]
)
