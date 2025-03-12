# Agentic Orchestration Framework

The Agent Gateway is an agentic orchestration framework that offers native support for Snowflake tools.

Instead of requiring users or developers to choose between RAG with Cortex Search or
Text2SQL with Cortex Analyst, the Agent Gateway orchestrates the request to the
appropriate tool.

The Agent Gateway can be configured to work with 3 types of tools:
- **Cortex Search Tool**: For unstructured data analysis, which requires a standard RAG
access pattern.
- **Cortex Analyst Tool**: For supporting structured data analysis, which requires a
Text2SQL access pattern.
- **Python Tool**: For supporting custom user operations (i.e. sending API requests to
third party services), which requires calling arbitrary python.

The Agent Gateway supports multi-step and multi-tool workflows. Users have the flexibility to create multiple Cortex Search and Cortex Analyst tools for use with the Agent Gateway. For a walkthrough of how to configure and run a system with all 3 types of tools, see the [Quickstart](Quickstart.ipynb) notebook.

This library is optimized for client-side orchestration. If you prefer a managed service, we recommend the Snowflake Chat API.

# Getting Started

## Installation

1. Create a conda environment and activate it.
```
conda create -n orchestration_framework python=3.11
conda activate orchestration_framework
```
2. Install the orchestration framework.
```
pip install git+https://github.com/Snowflake-Labs/orchestration-framework.git@truelens --force-reinstall
```

3. Configure `.env` file.

4. Demo:
    - In order to show Streamlit app, do ```
    cd demo_app
    streamlit run demo_app.py
    ```
    - In order to show Trulens integration, select `orchestration_framework` kernel and run `CX_AGENTS.ipynb`.

**Note For Mac Users**: Mac users have reported SSL Certificate issues when using the
Cortex REST API. This is related to python virtual environments not having access to
local certificates. One potential solution to avoid SSL Certificate issues is to use
Finder to locate the "Install Certificates.command" file in your relevant Python
directory and run that file before initializing the agent. See [this thread](https://github.com/python/cpython/issues/87570#issuecomment-1093904961) for more info.


# FAQs

#### Where does the Agent Gateway run?

- This library is optimized for client-side orchestration. If you prefer a managed service that does the orchestration inside of Snowflake, we recommend using the Snowflake Chat API.

#### Why is this library so good ?
The library has retries built in. For example, ask this question:

```
cx_agent("Give me the key details about the case with Ticket ID: f4fca2ad-84e4-4bc9-9f86-9bd3a0da3d33. Also, tell me how much the customer mentioned in the ticket has spent on rides")
```
Initial plan:
```
1. support_tickets_cortexanalyst("Give me the key details about the case with Ticket ID: f4fca2ad-84e4-4bc9-9f86-9bd3a0da3d33")
2. rides_cortexanalyst("How much has the customer mentioned in the ticket with Ticket ID: f4fca2ad-84e4-4bc9-9f86-9bd3a0da3d33 spent on rides?")
Thought: I can answer the question now.
3. fuse()<END_OF_PLAN>
```
and then:
```
1. support_tickets_cortexanalyst("Give me the customer ID associated with the Ticket ID: f4fca2ad-84e4-4bc9-9f86-9bd3a0da3d33")
2. rides_cortexanalyst("How much has the customer with ID: $1 spent on rides?")
3. fuse()
```

The initial plan it generated didn't fully account for the dependencies between the tools. so it generates a new plan as shown above. see how in the first plan it tries to use the ticket ID to lookup the amount spent in the rides table?. but the rides table doesn't have the Ticket ID so it throws that error.

#### Can I use the Agent Gateway within SPCS or a Snowflake Notebook?

- Yes, the Agent Gateway can run in SPCS and Snowflake notebooks backed by a container
runtime. To install the library directly from GitHub, you must enable a network rule
with an external access integration. Here is an example configuration:

```sql
CREATE NETWORK RULE agent_network_rule
MODE = EGRESS
TYPE = HOST_PORT
VALUE_LIST = ('github.com');

CREATE EXTERNAL ACCESS INTEGRATION agent_network_int
ALLOWED_NETWORK_RULES = (agent_network_rule)
ENABLED = true;
```

#### Does the Agent Gateway work with a Streamlit UI?

- Yes, see the [demo app](https://github.com/Snowflake-Labs/orchestration-framework/blob/main/demo_app/demo_app.py) for an example Streamlit app that uses the Agent Gateway for orchestration across Cortex Search, Cortex Analyst, and Python tools. Note, running the gateway is not yet supported in Stremlit in Snowflake.

#### How does authentication work?

- The Agent Gateway and its tools take an authenticated snowpark connection. Just create your session
object with your standard [connection parameters](https://docs.snowflake.com/en/developer-guide/snowpark/reference/python/latest/snowpark/api/snowflake.snowpark.Session).

#### If I have multiple Cortex Search Services, can I use multiple Cortex Search tools with this framework?

- Yes, you can connect multiple tools of the same type to the Agent Gateway.
```python
search_one = CortexSearchTool(**search_one_config)
search_two = CortexSearchTool(**search_two_config)
snowflake_agent = Agent(snowflake_connection=session, tools=[search_one, search_two])
```

#### If my Snowflake tools live in different accounts / schemas, can I still use the Agent Gateway?

- Yes. The Cortex Analyst and Cortex Search tools take in a snowpark session as an
input. This allows users to use different sessions / accounts in the same gateway agent.

#### How can I see which tools are being used by the Agent Gateway?

- The Agent Gateway logger is set to INFO level by default. This allows users to view
which tools are being used to answer the user's question. For more detailed logging and
visibility into intermediary results of the tool calls, set the LOGGING_LEVEL=DEBUG.

#### I'm not getting any results when I submit a request. How do I debug this?

- Tools are implemented asynchronously. To validate your configuration, you can run each tool in isolation as follows:
```python
tool_result = await my_cortex_search_tool("This is a sample cortex search question")
```

#### How does it work?

- This framework utilizes a dedicated planner LLM to generate a sequence of tool calls that can be executed in parallel. While the orchestration is done on the client-side, Snowflake compute is leveraged for plan generation and tooling execution. We leverage the LLM Compiler architecture from Berkeley AI Research Lab. Kim, S., Moon, S., Tabrizi, R., Lee, N., Mahoney, M. W., Keutzer, K., and Gholami, A. An LLM Compiler for Parallel Function Calling, 2024.

# Bug Reports, Feedback, or Other Questions

- You can add issues to the GitHub or email Alejandro Herrera (alejandro.herrera@snowflake.com)
