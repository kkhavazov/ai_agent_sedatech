

from customer_support_agent import customer_support_agent

# Configure a thread ID to maintain conversation state locally
config = {"configurable": {"thread_id": "test-session-1"}}

# Test 1: Inventory lookup query
response = customer_support_agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "how many 16 gb ddr5 rams do we have?",
            }
        ]
    },
    config,
)

print("--- Inventory Query Response ---")
print(response["messages"][-1])

# Test 2: RAG knowledge base query
# response = customer_support_agent.invoke(
#     {
#         "messages": [
#             {
#                 "role": "user",
#                 "content": "What is our official return policy for damaged goods?",
#             }
#         ]
#     },
#     config,
# )

# print("\n--- Knowledge Base Query Response ---")
# print(response)