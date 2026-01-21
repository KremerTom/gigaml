#!/usr/bin/env python3
"""Simple agent to query financial data."""
import sqlite3
import json
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=30)

# Connect to our test database
db = sqlite3.connect("data/database/test.db")
db.row_factory = sqlite3.Row

def get_company_data(company_name: str = None):
    """Get data for a company."""
    if company_name:
        row = db.execute("SELECT * FROM test_extract WHERE company LIKE ?", (f"%{company_name}%",)).fetchone()
    else:
        row = db.execute("SELECT * FROM test_extract").fetchone()
    if row:
        return {"company": row[0], "sector": row[1], "cmp": row[2], "target_price": row[3]}
    return {"error": "Company not found"}

def list_companies():
    """List all companies in database."""
    rows = db.execute("SELECT company, sector FROM test_extract").fetchall()
    return [{"company": r[0], "sector": r[1]} for r in rows]

# Tools for GPT-5
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_company_data",
            "description": "Get financial data for a company including current price and target price",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "Company name to look up"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_companies",
            "description": "List all companies in the database",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def run_agent(question: str):
    """Run agent with a question."""
    messages = [
        {"role": "system", "content": "You are a financial research assistant. Use the tools to answer questions about companies. Only answer based on data from tools - don't make things up."},
        {"role": "user", "content": question}
    ]
    
    response = client.chat.completions.create(
        model="gpt-5",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    msg = response.choices[0].message
    
    # Handle tool calls
    if msg.tool_calls:
        messages.append(msg)
        for tc in msg.tool_calls:
            fn = tc.function.name
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            
            if fn == "get_company_data":
                result = get_company_data(args.get("company_name"))
            elif fn == "list_companies":
                result = list_companies()
            else:
                result = {"error": "Unknown function"}
            
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
        
        # Get final response
        response = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            tools=tools
        )
        return response.choices[0].message.content
    
    return msg.content

if __name__ == "__main__":
    print("Financial Research Agent")
    print("=" * 40)
    print("Data: Hindalco Industries (test)")
    print("Type 'quit' to exit\n")
    
    while True:
        q = input("You: ").strip()
        if q.lower() in ('quit', 'exit', 'q'):
            break
        if not q:
            continue
        print(f"Agent: {run_agent(q)}\n")
