import os
import streamlit as st
from model_serving_utils import (
    endpoint_supports_feedback, 
    query_endpoint, 
    query_endpoint_stream, 
    _get_endpoint_task_type,
)
from collections import OrderedDict
from messages import UserMessage, AssistantResponse, render_message

def show_page():
    KBKA_SERVING_ENDPOINT = os.getenv('KBKA_SERVING_ENDPOINT')
    assert KBKA_SERVING_ENDPOINT, \
        ("Unable to determine serving endpoint to use for chatbot app. If developing locally, "
        "set the KBKA_SERVING_ENDPOINT environment variable to the name of your serving endpoint. If "
        "deploying to a Databricks app, include a serving endpoint resource named "
        "'kbka_serving_endpoint' with CAN_QUERY permissions, as described in "
        "https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app#deploy-the-databricks-app")

    KBKA_ENDPOINT_SUPPORTS_FEEDBACK = endpoint_supports_feedback(KBKA_SERVING_ENDPOINT)

    def reduce_chat_agent_chunks(chunks):
        """
        Reduce a list of ChatAgentChunk objects corresponding to a particular
        message into a single ChatAgentMessage
        """
        deltas = [chunk.delta for chunk in chunks]
        first_delta = deltas[0]
        result_msg = first_delta
        msg_contents = []
        
        tool_call_map = {}  
        
        for delta in deltas:
            if delta.content:
                msg_contents.append(delta.content)
                
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    call_id = getattr(tool_call, 'id', None)
                    tool_type = getattr(tool_call, 'type', "function")
                    function_info = getattr(tool_call, 'function', None)
                    if function_info:
                        func_name = getattr(function_info, 'name', "")
                        func_args = getattr(function_info, 'arguments', "")
                    else:
                        func_name = ""
                        func_args = ""
                    
                    if call_id:
                        if call_id not in tool_call_map:
                            tool_call_map[call_id] = {
                                "id": call_id,
                                "type": tool_type,
                                "function": {
                                    "name": func_name,
                                    "arguments": func_args
                                }
                            }
                        else:
                            existing_args = tool_call_map[call_id]["function"]["arguments"]
                            tool_call_map[call_id]["function"]["arguments"] = existing_args + func_args

                            if func_name:
                                tool_call_map[call_id]["function"]["name"] = func_name

            if hasattr(delta, 'tool_call_id') and delta.tool_call_id:
                result_msg = result_msg.model_copy(update={"tool_call_id": delta.tool_call_id})
        
        if tool_call_map:
            accumulated_tool_calls = list(tool_call_map.values())
            result_msg = result_msg.model_copy(update={"tool_calls": accumulated_tool_calls})
        
        result_msg = result_msg.model_copy(update={"content": "".join(msg_contents)})
        return result_msg

    if "kb_history" not in st.session_state:
        st.session_state.kb_history = []

    st.title("Assisted-Learning Portal")
    st.write(f"Endpoint name: `{KBKA_SERVING_ENDPOINT}`")
    for i, element in enumerate(st.session_state.kb_history):
        element.render(i)

    def query_endpoint_and_render(task_type, input_messages):
        """Handle streaming response based on task type."""
        if task_type == "agent/v1/responses":
            return query_responses_endpoint_and_render(input_messages)
        elif task_type == "agent/v2/chat":
            return query_chat_agent_endpoint_and_render(input_messages)
        else:
            return query_chat_completions_endpoint_and_render(input_messages)


    def query_chat_completions_endpoint_and_render(input_messages):
        """Handle ChatCompletions streaming format."""
        with st.chat_message("assistant"):
            response_area = st.empty()
            response_area.markdown("_Thinking..._")
            
            accumulated_content = ""
            request_id = None
            
            try:
                for chunk in query_endpoint_stream(
                    endpoint_name=KBKA_SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=KBKA_ENDPOINT_SUPPORTS_FEEDBACK
                ):
                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            accumulated_content += content
                            response_area.markdown(accumulated_content)
                    
                    if "databricks_output" in chunk:
                        req_id = chunk["databricks_output"].get("databricks_request_id")
                        if req_id:
                            request_id = req_id
                
                return AssistantResponse(
                    messages=[{"role": "assistant", "content": accumulated_content}],
                    request_id=request_id
                )
            except Exception:
                response_area.markdown("_Ran into an error. Retrying without streaming..._")
                messages, request_id = query_endpoint(
                    endpoint_name=KBKA_SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=KBKA_ENDPOINT_SUPPORTS_FEEDBACK
                )
                response_area.empty()
                with response_area.container():
                    for message in messages:
                        render_message(message)
                return AssistantResponse(messages=messages, request_id=request_id)


    def query_chat_agent_endpoint_and_render(input_messages):
        """Handle ChatAgent streaming format."""
        from mlflow.types.agent import ChatAgentChunk
        
        with st.chat_message("assistant"):
            response_area = st.empty()
            response_area.markdown("_Thinking..._")
            
            message_buffers = OrderedDict()
            request_id = None
            
            try:
                for raw_chunk in query_endpoint_stream(
                    endpoint_name=KBKA_SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=KBKA_ENDPOINT_SUPPORTS_FEEDBACK
                ):
                    response_area.empty()
                    chunk = ChatAgentChunk.model_validate(raw_chunk)
                    delta = chunk.delta
                    message_id = delta.id

                    req_id = raw_chunk.get("databricks_output", {}).get("databricks_request_id")
                    if req_id:
                        request_id = req_id
                    if message_id not in message_buffers:
                        message_buffers[message_id] = {
                            "chunks": [],
                            "render_area": st.empty(),
                        }
                    message_buffers[message_id]["chunks"].append(chunk)
                    
                    partial_message = reduce_chat_agent_chunks(message_buffers[message_id]["chunks"])
                    render_area = message_buffers[message_id]["render_area"]
                    message_content = partial_message.model_dump_compat(exclude_none=True)
                    with render_area.container():
                        render_message(message_content)
                
                messages = []
                for msg_id, msg_info in message_buffers.items():
                    messages.append(reduce_chat_agent_chunks(msg_info["chunks"]))
                
                return AssistantResponse(
                    messages=[message.model_dump_compat(exclude_none=True) for message in messages],
                    request_id=request_id
                )
            except Exception:
                response_area.markdown("_Ran into an error. Retrying without streaming..._")
                messages, request_id = query_endpoint(
                    endpoint_name=KBKA_SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=KBKA_ENDPOINT_SUPPORTS_FEEDBACK
                )
                response_area.empty()
                with response_area.container():
                    for message in messages:
                        render_message(message)
                return AssistantResponse(messages=messages, request_id=request_id)


    def query_responses_endpoint_and_render(input_messages):
        """Handle ResponsesAgent streaming format using MLflow types."""
        from mlflow.types.responses import ResponsesAgentStreamEvent
        
        with st.chat_message("assistant"):
            response_area = st.empty()
            response_area.markdown("_Thinking..._")
            
            all_messages = []
            request_id = None

            try:
                for raw_event in query_endpoint_stream(
                    endpoint_name=KBKA_SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=KBKA_ENDPOINT_SUPPORTS_FEEDBACK
                ):
                    if "databricks_output" in raw_event:
                        req_id = raw_event["databricks_output"].get("databricks_request_id")
                        if req_id:
                            request_id = req_id
                    
                    if "type" in raw_event:
                        event = ResponsesAgentStreamEvent.model_validate(raw_event)
                        
                        if hasattr(event, 'item') and event.item:
                            item = event.item 
                            
                            if item.get("type") == "message":
                                content_parts = item.get("content", [])
                                for content_part in content_parts:
                                    if content_part.get("type") == "output_text":
                                        text = content_part.get("text", "")
                                        if text:
                                            all_messages.append({
                                                "role": "assistant",
                                                "content": text
                                            })
                                
                            elif item.get("type") == "function_call":
                                call_id = item.get("call_id")
                                function_name = item.get("name")
                                arguments = item.get("arguments", "")
                                all_messages.append({
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [{
                                        "id": call_id,
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments
                                        }
                                    }]
                                })
                                
                            elif item.get("type") == "function_call_output":
                                call_id = item.get("call_id")
                                output = item.get("output", "")
                                all_messages.append({
                                    "role": "tool",
                                    "content": output,
                                    "tool_call_id": call_id
                                })
                    
                    if all_messages:
                        with response_area.container():
                            for msg in all_messages:
                                render_message(msg)

                return AssistantResponse(messages=all_messages, request_id=request_id)
            except Exception:
                response_area.markdown("_Ran into an error. Retrying without streaming..._")
                messages, request_id = query_endpoint(
                    endpoint_name=KBKA_SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=KBKA_ENDPOINT_SUPPORTS_FEEDBACK
                )
                response_area.empty()
                with response_area.container():
                    for message in messages:
                        render_message(message)
                return AssistantResponse(messages=messages, request_id=request_id)

    suggestive_topics = {
        "Billing and Refunds": [
            "Help with billing questions, overcharges, duplicate charges, and unauthorized charges.",
            "Assistance with refunds for unused services, service cancellations, equipment returns, and billing errors.",
            "Support for plan changes, including prorated credits or refunds.",
            "Guidance on non-refundable items and special circumstances (e.g., contract termination, deceased customers).",
        ],
        "Technical Support": [
            "Troubleshooting for service issues such as network outages, device problems, and connectivity.",
            "Device setup assistance, both in-store and remotely (phone, video, app).",
            "Help with home installation for internet and networking equipment.",
            "Maintenance notifications and updates.",
        ],
        "Device Returns": [
            "Support for returning devices and accessories within specified timeframes.",
            "Processing of refunds or replacements for defective equipment.",
            "Information on restocking fees and required documentation.",
        ],
        "Service Interruption": [
            "Compensation for service outages or interruptions, calculated based on outage duration and plan cost.",
            "Automatic credits for widespread outages; manual requests for individual issues.",
            "Guidance on eligibility and how to request credits.",
        ],
        "Dispute Resolution": [
            "Formal review and appeal processes for denied refund or credit requests.",
            "Assistance with submitting dispute forms and escalation to resolution departments.",
        ],
        "Account Management": [
            "Account access and management via website, mobile app, phone, and retail locations.",
            "Notifications about service status, outages, maintenance, and policy changes.",
            "Customizable communication preferences.",
        ],
    }

    if "selected_topic" not in st.session_state:
        st.session_state.selected_topic = None
    if "selected_question" not in st.session_state:
        st.session_state.selected_question = None

    st.markdown("##### 💡 Explore Knowledge Base Topics")
    topic_cols = st.columns(len(suggestive_topics))
    for i, topic in enumerate(suggestive_topics.keys()):
        with topic_cols[i]:
            if st.button(topic, use_container_width=True, key=f"topic_{i}"):
                st.session_state.selected_topic = topic
                st.session_state.selected_question = None  # Reset question when topic changes

    if st.session_state.selected_topic:
        st.markdown(f"##### Suggested Questions for **{st.session_state.selected_topic}**")

        question_cols = st.columns(2)
        questions = suggestive_topics[st.session_state.selected_topic]

        for idx, q in enumerate(questions):
            with question_cols[idx % 2]:
                if st.button(q, key=f"question_{idx}"):
                    st.session_state.selected_question = q

    prompt = None
    if st.session_state.selected_question:
        prompt = st.session_state.selected_question
        st.info(f"💬 Selected question: {prompt}")
    else:
        prompt = st.chat_input("Ask a question about the knowledge base")
    if prompt:
        task_type = _get_endpoint_task_type(KBKA_SERVING_ENDPOINT)
        
        user_msg = UserMessage(content=prompt)
        st.session_state.kb_history.append(user_msg)
        user_msg.render(len(st.session_state.kb_history) - 1)

        input_messages = [msg for elem in st.session_state.kb_history for msg in elem.to_input_messages()]
        assistant_response = query_endpoint_and_render(task_type, input_messages)
        st.session_state.kb_history.append(assistant_response)
