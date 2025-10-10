import os
import re
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

    # Ensure environment variable is set correctly
    SERVING_ENDPOINT = os.getenv('SERVING_ENDPOINT')
    assert SERVING_ENDPOINT, \
        ("Unable to determine serving endpoint to use for chatbot app. If developing locally, "
        "set the SERVING_ENDPOINT environment variable to the name of your serving endpoint. If "
        "deploying to a Databricks app, include a serving endpoint resource named "
        "'serving_endpoint' with CAN_QUERY permissions, as described in "
        "https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app#deploy-the-databricks-app")

    ENDPOINT_SUPPORTS_FEEDBACK = endpoint_supports_feedback(SERVING_ENDPOINT)

    def is_live_agent_request(user_input):
        """
        Check if user input contains keywords indicating they want to connect to a live agent/advisor.
        """
        # Convert to lowercase for case-insensitive matching
        input_lower = user_input.lower()
        
        # Keywords that indicate user wants to talk to a human
        live_agent_keywords = [
            "connect to live agent", "transfer to live agent", "escalate my case"
        ]
        
        # Check if any of the keywords appear in the user input
        for keyword in live_agent_keywords:
            if keyword in input_lower:
                return True
        
        return False

    def show_live_agent_modal():
        """
        Show a modal dialog for live agent connection.
        """
        # Add custom CSS for live agent interface
        st.markdown("""
        <style>
        .live-agent-header {
            background: linear-gradient(90deg, #28a745, #20c997);
            color: white;
            padding: 1rem;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 1rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .live-agent-status {
            background-color: #e8f5e8;
            color: #28a745;
            padding: 0.5rem;
            border-radius: 5px;
            text-align: center;
            margin-bottom: 1rem;
            border-left: 4px solid #28a745;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Header for live agent interface
        st.markdown("""
        <div class="live-agent-header">
            <h2>🧑‍💼 Live Support Agent - Sarah</h2>
            <p>You're now chatting with a real person who's here to help!</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Status indicator
        st.markdown("""
        <div class="live-agent-status">
            🟢 <strong>Agent Online</strong> - Average response time: 1-2 minutes
        </div>
        """, unsafe_allow_html=True)
        
        # Initialize live agent chat history if not exists
        if "live_agent_history" not in st.session_state:
            st.session_state.live_agent_history = [
                {"role": "agent", "content": "Hello! I'm Sarah, your live support agent. How may I help you today?"}
            ]
        
        # Display live agent chat history
        for i, msg in enumerate(st.session_state.live_agent_history):
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant", avatar="🧑‍💼"):
                    st.markdown(f"**Sarah (Live Agent):** {msg['content']}")
        
        # Live agent chat input
        live_agent_input = st.chat_input("Type your message to the live agent...", key="live_agent_input")
        
        if live_agent_input:
            # Add user message to live agent history
            st.session_state.live_agent_history.append({
                "role": "user", 
                "content": live_agent_input
            })
            
            # Simulate agent response (in a real implementation, this would connect to actual live agent system)
            agent_response = generate_live_agent_response(live_agent_input)
            st.session_state.live_agent_history.append({
                "role": "agent", 
                "content": agent_response
            })
            
            st.rerun()
        
        # Control buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("🔄 Back to AI Assistant", type="primary", key="back-to-ai"):
                # Add farewell message from agent
                farewell_message = {
                    "role": "agent", 
                    "content": "Thank you for contacting support! I'm ending our live chat session now. You'll be redirected back to the AI Assistant for any additional questions. Have a great day! 👋"
                }
                st.session_state.live_agent_history.append(farewell_message)
                
                # End the live agent session and return to AI assistant
                st.session_state.live_agent_active = False
                st.session_state.live_agent_history = []
                
                # Add session ended message to main chat history
                session_end_msg = AssistantResponse(
                    messages=[{
                        "role": "assistant", 
                        "content": "🔄 **Returned from Live Agent** - Your live support session has ended successfully. I'm your AI Assistant and I'm ready to help with any additional questions you may have!"
                    }],
                    request_id=None
                )
                st.session_state.history.append(session_end_msg)
                st.rerun()
        
        with col3:
            if st.button("❌ End Chat", type="secondary", key="end-chat"):
                # Set flag to show feedback request
                st.session_state.show_feedback = True
                st.rerun()
        
        # Show feedback section only when requested
        if st.session_state.get("show_feedback", False):
            # Add a farewell message from the agent before ending
            farewell_message = {
                "role": "agent", 
                "content": "Thank you for contacting support today! I hope I was able to help resolve your concerns. If you need any further assistance, please don't hesitate to reach out again. Have a great day! 👋"
            }
            if farewell_message not in st.session_state.live_agent_history:
                st.session_state.live_agent_history.append(farewell_message)
            
            # Show the farewell message immediately
            with st.chat_message("assistant", avatar="🧑‍💼"):
                st.markdown(f"**Sarah (Live Agent):** {farewell_message['content']}")
            
            # Show a comprehensive end chat message
            st.markdown("""
            <div style="background: linear-gradient(90deg, #17a2b8, #007bff); color: white; padding: 1.5rem; border-radius: 10px; text-align: center; margin: 1rem 0; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <h3>📞 Live Chat Session Ended</h3>
                <p><strong>Thank you for contacting our support team!</strong></p>
                <p>Your conversation with Sarah has been concluded. We hope we were able to help resolve your issue.</p>
                <hr style="border-color: rgba(255,255,255,0.3); margin: 1rem 0;">
                <p><small>💡 <strong>Need more help?</strong> You can always start a new chat session or continue with our AI Assistant.</small></p>
                <p><small>📧 <strong>Feedback:</strong> Please rate your experience to help us improve our service.</small></p>
            </div>
            """, unsafe_allow_html=True)
            
            # Add feedback buttons that automatically end the chat
            col_feedback1, col_feedback2, col_feedback3 = st.columns(3)
            with col_feedback1:
                if st.button("😊 Excellent", key="feedback_excellent"):
                    st.balloons()
                    st.success("Thank you for your excellent feedback! Returning to AI Assistant...")
                    # End chat session immediately after feedback
                    st.session_state.live_agent_active = False
                    st.session_state.live_agent_history = []
                    st.session_state.show_feedback = False
                    # Add session ended message to main chat history
                    session_end_msg = AssistantResponse(
                        messages=[{
                            "role": "assistant", 
                            "content": "🔚 **Live Agent Session Ended** - Thank you for your excellent feedback! Your session with our live support agent has been successfully concluded. I'm back to assist you with any other questions you may have."
                        }],
                        request_id=None
                    )
                    st.session_state.history.append(session_end_msg)
                    st.rerun()
                    
            with col_feedback2:
                if st.button("😐 Average", key="feedback_average"):
                    st.info("Thank you for your feedback! Returning to AI Assistant...")
                    # End chat session immediately after feedback
                    st.session_state.live_agent_active = False
                    st.session_state.live_agent_history = []
                    st.session_state.show_feedback = False
                    # Add session ended message to main chat history
                    session_end_msg = AssistantResponse(
                        messages=[{
                            "role": "assistant", 
                            "content": "🔚 **Live Agent Session Ended** - Thank you for your feedback! Your session with our live support agent has been concluded. We appreciate your input and will use it to improve our service. How else can I assist you?"
                        }],
                        request_id=None
                    )
                    st.session_state.history.append(session_end_msg)
                    st.rerun()
                    
            with col_feedback3:
                if st.button("😞 Poor", key="feedback_poor"):
                    st.warning("Thank you for your feedback! Returning to AI Assistant...")
                    # End chat session immediately after feedback
                    st.session_state.live_agent_active = False
                    st.session_state.live_agent_history = []
                    st.session_state.show_feedback = False
                    # Add session ended message to main chat history
                    session_end_msg = AssistantResponse(
                        messages=[{
                            "role": "assistant", 
                            "content": "🔚 **Live Agent Session Ended** - Thank you for your honest feedback. Your session with our live support agent has been concluded. We sincerely apologize if we didn't meet your expectations and will work hard to improve. Is there anything else I can help you with?"
                        }],
                        request_id=None
                    )
                    st.session_state.history.append(session_end_msg)
                    st.rerun()
        
        st.markdown("---")

    def generate_live_agent_response(user_message):
        """
        Generate a simulated live agent response.
        In a real implementation, this would connect to your live agent system.
        """
        import random
        import time
        
        # Simple pattern-based responses for demonstration
        message_lower = user_message.lower()
        
        # Greeting responses
        if any(word in message_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon"]):
            responses = [
                "Hello! Thanks for contacting support. I'm Sarah and I'll be assisting you today. How can I help?",
                "Hi there! I'm glad you reached out. What can I help you with today?",
                "Good day! I'm here to help resolve any issues you might be experiencing. What's going on?"
            ]
            return random.choice(responses)

        # Account-related responses
        elif any(word in message_lower for word in ["account", "login", "password", "username", "sign in"]):
            responses = [
                "I can definitely help with account issues. For security purposes, I'll need to verify your identity. Can you please provide the email address associated with your account?",
                "Account access problems can be resolved quickly. Let me assist you with that. What's the email address you use to log in?",
                "I'm here to help with your account. To protect your privacy, could you please confirm your account email address?"
            ]
            return random.choice(responses)
        
        # Billing responses
        elif any(word in message_lower for word in ["billing", "payment", "charge", "invoice"]):
            # Find which word was matched for more personalized response
            matched_word = next((word for word in ["billing", "payment", "charge", "invoice"] if word in message_lower), "billing")
            responses = [
                f"I can assist with {matched_word} inquiries. Let me pull up your account information. Can you please confirm your account email address?",
                f"I understand you have questions about {matched_word}. I'll be happy to review your account details. What's your account email?",
                f"{matched_word.capitalize()} questions are something I can help with right away. For security, I'll need to verify your account email address first."
            ]
            return random.choice(responses)
        
            # Problem/issue responses
        elif any(word in message_lower for word in ["broken", "not working"]):
            responses = [
                "I'm sorry to hear you're experiencing difficulties. Let me help you resolve this. Can you describe exactly what's happening when you encounter this issue?",
                "I understand this must be frustrating. To better assist you, could you please provide more specific details about the problem?",
                "Let me look into this for you right away. Can you walk me through the steps you took when this issue occurred?"
            ]
            return random.choice(responses)
        
        # Refund/cancellation responses  
        elif any(word in message_lower for word in ["refund", "cancel", "return", "money back"]):
            responses = [
                "I'm so sorry that we didn't meet your expectations. Let me see what I can do to make this right for you, including a one-time goodwill credit if appropriate. Can you tell me more about your specific situation?",
                "I sincerely apologize that you're not satisfied with your experience. I'd be happy to process a refund or offer a goodwill gesture to resolve this. What exactly happened that led to this request?",
                "I'm truly sorry we fell short of your expectations. Let me help make this right immediately - whether that's a full refund, partial credit, or other compensation. Can you walk me through what went wrong?"
            ]
            return random.choice(responses)
        
        # Technical support
        elif any(word in message_lower for word in ["technical", "tech", "service"]):
            responses = [
                "I can help with technical issues. Let me connect you with our tech support team or try to resolve this myself. What device and browser are you using?",
                "Technical problems can usually be resolved quickly. Can you describe the specific behavior you're seeing and what device you're using?",
                "I'm here to help with technical difficulties. What exactly is happening, and have you tried refreshing the page or restarting the app?"
            ]
            return random.choice(responses)
        
        # Gratitude responses
        elif any(word in message_lower for word in ["thank", "thanks", "appreciate","resolved"]):
            responses = [
                "Happy to help! It was my pleasure assisting you today. When you're ready to wrap up, please use the 'End Chat' button to provide quick feedback - it really helps us improve our service. Please don't hesitate to reach out if you need anything else.",
                "My pleasure! I'm thrilled we could get this sorted out for you. Before you go, feel free to hit 'End Chat' and share your experience in our quick feedback survey. Let me know if you have any other questions or concerns."
            ]
            return random.choice(responses)
        
        # Default response
        else:
            responses = [
                "Thank you for contacting support. I'm here to help with whatever you need. Can you please provide more details about how I can assist you?",
                "I'm ready to help! Could you give me a bit more information about what you're looking for assistance with?",
                "I want to make sure I give you the best possible help. Can you elaborate on what specific issue or question you have?"
            ]
            return random.choice(responses)

    def reduce_chat_agent_chunks(chunks):
        """
        Reduce a list of ChatAgentChunk objects corresponding to a particular
        message into a single ChatAgentMessage
        """
        deltas = [chunk.delta for chunk in chunks]
        first_delta = deltas[0]
        result_msg = first_delta
        msg_contents = []
        
        # Accumulate tool calls properly
        tool_call_map = {}  # Map call_id to tool call for accumulation
        
        for delta in deltas:
            # Handle content
            if delta.content:
                msg_contents.append(delta.content)
                
            # Handle tool calls
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
                            # New tool call
                            tool_call_map[call_id] = {
                                "id": call_id,
                                "type": tool_type,
                                "function": {
                                    "name": func_name,
                                    "arguments": func_args
                                }
                            }
                        else:
                            # Accumulate arguments for existing tool call
                            existing_args = tool_call_map[call_id]["function"]["arguments"]
                            tool_call_map[call_id]["function"]["arguments"] = existing_args + func_args

                            # Update function name if provided
                            if func_name:
                                tool_call_map[call_id]["function"]["name"] = func_name

            # Handle tool call IDs (for tool response messages)
            if hasattr(delta, 'tool_call_id') and delta.tool_call_id:
                result_msg = result_msg.model_copy(update={"tool_call_id": delta.tool_call_id})
        
        # Convert tool call map back to list
        if tool_call_map:
            accumulated_tool_calls = list(tool_call_map.values())
            result_msg = result_msg.model_copy(update={"tool_calls": accumulated_tool_calls})
        
        result_msg = result_msg.model_copy(update={"content": "".join(msg_contents)})
        return result_msg



    # --- Init state ---
    if "history" not in st.session_state:
        st.session_state.history = []

    if "live_agent_active" not in st.session_state:
        st.session_state.live_agent_active = False

    if "live_agent_history" not in st.session_state:
        st.session_state.live_agent_history = []

    if "show_feedback" not in st.session_state:
        st.session_state.show_feedback = False

    st.title("AI Assistant")
    # st.write(f"A basic chatbot using your own serving endpoint.")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"Endpoint name: `{SERVING_ENDPOINT}`")
    with col2:
        if st.button("🔄 New Chat", key="new-chat",type="secondary", help="Clear chat history and start fresh"):
            st.session_state.history = []
            st.session_state.live_agent_active = False
            st.session_state.live_agent_history = []
            st.session_state.show_feedback = False
            st.success("✨ Chat cleared! Ready for a new conversation.")
            st.rerun()

    # Show live agent interface if active
    if st.session_state.live_agent_active:
        show_live_agent_modal()
        st.stop()  # Stop rendering the rest of the page when live agent is active



    # --- Render chat history ---
    for i, element in enumerate(st.session_state.history):
        element.render(i)

    def query_endpoint_and_render(task_type, input_messages):
        """Handle streaming response based on task type."""
        if task_type == "agent/v1/responses":
            return query_responses_endpoint_and_render(input_messages)
        elif task_type == "agent/v2/chat":
            return query_chat_agent_endpoint_and_render(input_messages)
        else:  # chat/completions
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
                    endpoint_name=SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=ENDPOINT_SUPPORTS_FEEDBACK
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
                    endpoint_name=SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=ENDPOINT_SUPPORTS_FEEDBACK
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
                    endpoint_name=SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=ENDPOINT_SUPPORTS_FEEDBACK
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
                    endpoint_name=SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=ENDPOINT_SUPPORTS_FEEDBACK
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
            
            # Track all the messages that need to be rendered in order
            all_messages = []
            request_id = None

            try:
                for raw_event in query_endpoint_stream(
                    endpoint_name=SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=ENDPOINT_SUPPORTS_FEEDBACK
                ):
                    # Extract databricks_output for request_id
                    if "databricks_output" in raw_event:
                        req_id = raw_event["databricks_output"].get("databricks_request_id")
                        if req_id:
                            request_id = req_id
                    
                    # Parse using MLflow streaming event types, similar to ChatAgentChunk
                    if "type" in raw_event:
                        event = ResponsesAgentStreamEvent.model_validate(raw_event)
                        
                        if hasattr(event, 'item') and event.item:
                            item = event.item  # This is a dict, not a parsed object
                            
                            if item.get("type") == "message":
                                # Extract text content from message if present
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
                                # Tool call
                                call_id = item.get("call_id")
                                function_name = item.get("name")
                                arguments = item.get("arguments", "")
                                
                                # Add to messages for history
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
                                # Tool call output/result
                                call_id = item.get("call_id")
                                output = item.get("output", "")
                                
                                # Add to messages for history
                                all_messages.append({
                                    "role": "tool",
                                    "content": output,
                                    "tool_call_id": call_id
                                })
                    
                    # Update the display by rendering all accumulated messages
                    if all_messages:
                        with response_area.container():
                            for msg in all_messages:
                                render_message(msg)

                return AssistantResponse(messages=all_messages, request_id=request_id)
            except Exception:
                response_area.markdown("_Ran into an error. Retrying without streaming..._")
                messages, request_id = query_endpoint(
                    endpoint_name=SERVING_ENDPOINT,
                    messages=input_messages,
                    return_traces=ENDPOINT_SUPPORTS_FEEDBACK
                )
                response_area.empty()
                with response_area.container():
                    for message in messages:
                        render_message(message)
                return AssistantResponse(messages=messages, request_id=request_id)




    # --- Chat input (must run BEFORE rendering messages) ---
    prompt = st.chat_input("Ask a question or type 'connect to live agent' for human support")
    if prompt:
        # Check if user wants to connect to live agent
        if is_live_agent_request(prompt):
            # Add user message to chat history
            user_msg = UserMessage(content=prompt)
            st.session_state.history.append(user_msg)
            user_msg.render(len(st.session_state.history) - 1)
            
            # Add system message about connecting to live agent
            system_response = AssistantResponse(
                messages=[{
                    "role": "assistant", 
                    "content": "🔄 **Connecting you to a live agent...** Please wait a moment while I transfer you to one of our support representatives."
                }],
                request_id=None
            )
            st.session_state.history.append(system_response)
            system_response.render(len(st.session_state.history) - 1)
            
            # Activate live agent mode
            st.session_state.live_agent_active = True
            st.rerun()
        else:
            # Normal AI assistant flow
            # Get the task type for this endpoint
            task_type = _get_endpoint_task_type(SERVING_ENDPOINT)
            
            # Add user message to chat history
            user_msg = UserMessage(content=prompt)
            st.session_state.history.append(user_msg)
            user_msg.render(len(st.session_state.history) - 1)

            # Convert history to standard chat message format for the query methods
            input_messages = [msg for elem in st.session_state.history for msg in elem.to_input_messages()]
            
            # Handle the response using the appropriate handler
            assistant_response = query_endpoint_and_render(task_type, input_messages)
            
            # Add assistant response to history
            st.session_state.history.append(assistant_response)
