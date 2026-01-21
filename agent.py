#!/usr/bin/env python3
"""Financial Research Agent - Multi-turn conversational AI."""
import sqlite3
import json
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

DB_PATH = "data/database/financial_data.db"


class FinancialAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.conversation = []
        self.tools = self._define_tools()
        self.system_prompt = """You are a financial research assistant analyzing Indian equity research reports.

CRITICAL RULES:
- ONLY answer based on data from your tools - never make up numbers
- If data is missing, say "I don't have that data in my database"
- If a company isn't in the database, say so
- Always cite the source (which tool/query gave you the data)
- For multi-turn queries, use context from prior messages

Available data types:
- Company info: name, sector, codes
- Market data: CMP, target price, market cap, PE, PB, etc.
- Shareholding: promoter %, FII %, MF % by quarter
- Forecasts: Sales, EBITDA, PAT, EPS projections (FY24A, FY25E, FY26E)
- Financial statements: P&L, Balance Sheet, Cash Flow, Ratios (time series)
- Qualitative: business highlights, analysis text"""

    def _define_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_companies",
                    "description": "Get list of all companies in the database with their sectors",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_metrics",
                    "description": "Get all metrics for a company (market data, forecasts, shareholding)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name (partial match OK)"}
                        },
                        "required": ["company_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_time_series",
                    "description": "Get financial statement time series (P&L, Balance Sheet, Cash Flow, Ratios)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "table_name": {"type": "string", "enum": ["annual_pnl", "quarterly_pnl", "balance_sheet", "cash_flow", "ratios"], "description": "Which financial statement"}
                        },
                        "required": ["company_name", "table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_database",
                    "description": "Run a custom SQL query for complex questions. Tables: companies, metrics, time_series, qualitative",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "SQL query to execute"}
                        },
                        "required": ["sql"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_qualitative",
                    "description": "Get qualitative text (business highlights, analysis) for a company",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"}
                        },
                        "required": ["company_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_companies",
                    "description": "Compare a specific metric across all companies",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric_name": {"type": "string", "description": "Metric to compare (e.g., market_cap_cr, cmp, target_price, pe, roe)"},
                            "sort_order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort ascending or descending"}
                        },
                        "required": ["metric_name"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "get_schema",
                    "description": "Get database schema - list of tables and available metrics",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]

    # Tool implementations
    def list_companies(self):
        rows = self.db.execute("SELECT name, sector FROM companies").fetchall()
        return [{"name": r["name"], "sector": r["sector"]} for r in rows]

    def get_company_metrics(self, company_name: str):
        # Find company
        company = self.db.execute(
            "SELECT id, name, sector FROM companies WHERE name LIKE ?", 
            (f"%{company_name}%",)
        ).fetchone()
        if not company:
            return {"error": f"Company '{company_name}' not found"}
        
        # Get all metrics
        metrics = self.db.execute(
            "SELECT field_name, value, unit, time_period FROM metrics WHERE company_id = ?",
            (company["id"],)
        ).fetchall()
        
        result = {
            "company": company["name"],
            "sector": company["sector"],
            "metrics": {}
        }
        for m in metrics:
            key = m["field_name"]
            if m["time_period"]:
                key = f"{key}_{m['time_period']}"
            result["metrics"][key] = {"value": m["value"], "unit": m["unit"]}
        
        return result

    def get_time_series(self, company_name: str, table_name: str):
        company = self.db.execute(
            "SELECT id, name FROM companies WHERE name LIKE ?",
            (f"%{company_name}%",)
        ).fetchone()
        if not company:
            return {"error": f"Company '{company_name}' not found"}
        
        rows = self.db.execute(
            "SELECT metric, period, value, unit FROM time_series WHERE company_id = ? AND table_name LIKE ?",
            (company["id"], f"%{table_name}%")
        ).fetchall()
        
        # Pivot to metric -> {period: value}
        data = {}
        for r in rows:
            metric = r["metric"]
            if metric not in data:
                data[metric] = {"unit": r["unit"], "values": {}}
            data[metric]["values"][r["period"]] = r["value"]
        
        return {"company": company["name"], "table": table_name, "data": data}

    def query_database(self, sql: str):
        try:
            # Basic safety check
            if any(kw in sql.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                return {"error": "Only SELECT queries allowed"}
            rows = self.db.execute(sql).fetchall()
            return [dict(r) for r in rows[:50]]  # Limit results
        except Exception as e:
            return {"error": str(e)}

    def get_qualitative(self, company_name: str):
        company = self.db.execute(
            "SELECT id, name FROM companies WHERE name LIKE ?",
            (f"%{company_name}%",)
        ).fetchone()
        if not company:
            return {"error": f"Company '{company_name}' not found"}
        
        rows = self.db.execute(
            "SELECT chunk_type, content, page_num FROM qualitative WHERE company_id = ?",
            (company["id"],)
        ).fetchall()
        
        return {
            "company": company["name"],
            "sections": [{"type": r["chunk_type"], "content": r["content"], "page": r["page_num"]} for r in rows]
        }

    def compare_companies(self, metric_name: str, sort_order: str = "desc"):
        order = "DESC" if sort_order == "desc" else "ASC"
        rows = self.db.execute(f"""
            SELECT c.name, c.sector, m.value, m.unit 
            FROM metrics m 
            JOIN companies c ON m.company_id = c.id 
            WHERE m.field_name LIKE ?
            ORDER BY m.value {order}
        """, (f"%{metric_name}%",)).fetchall()
        
        return [{"company": r["name"], "sector": r["sector"], "value": r["value"], "unit": r["unit"]} for r in rows]

    def get_schema(self):
        # Get unique field names
        metrics = self.db.execute("SELECT DISTINCT field_name FROM metrics ORDER BY field_name").fetchall()
        ts_tables = self.db.execute("SELECT DISTINCT table_name FROM time_series").fetchall()
        ts_metrics = self.db.execute("SELECT DISTINCT metric FROM time_series ORDER BY metric").fetchall()
        
        return {
            "tables": ["companies", "metrics", "time_series", "qualitative"],
            "metric_fields": [r[0] for r in metrics],
            "time_series_tables": [r[0] for r in ts_tables],
            "time_series_metrics": [r[0] for r in ts_metrics][:30]  # Limit
        }

    def _execute_tool(self, name: str, args: dict):
        if name == "list_companies":
            return self.list_companies()
        elif name == "get_company_metrics":
            return self.get_company_metrics(args["company_name"])
        elif name == "get_time_series":
            return self.get_time_series(args["company_name"], args["table_name"])
        elif name == "query_database":
            return self.query_database(args["sql"])
        elif name == "get_qualitative":
            return self.get_qualitative(args["company_name"])
        elif name == "compare_companies":
            return self.compare_companies(args["metric_name"], args.get("sort_order", "desc"))
        elif name == "get_schema":
            return self.get_schema()
        return {"error": "Unknown tool"}

    def ask(self, question: str) -> str:
        """Process a question with multi-turn context."""
        self.conversation.append({"role": "user", "content": question})
        
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation
        
        response = self.client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            tools=self.tools,
            tool_choice="auto",
        )
        
        msg = response.choices[0].message
        
        # Handle tool calls (possibly multiple rounds)
        while msg.tool_calls:
            self.conversation.append(msg)
            
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                result = self._execute_tool(tc.function.name, args)
                self.conversation.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str)
                })
            
            messages = [{"role": "system", "content": self.system_prompt}] + self.conversation
            response = self.client.chat.completions.create(
                model="gpt-5",
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
            )
            msg = response.choices[0].message
        
        answer = msg.content
        self.conversation.append({"role": "assistant", "content": answer})
        return answer

    def reset(self):
        """Clear conversation history."""
        self.conversation = []


def main():
    print("=" * 50)
    print("Financial Research Agent")
    print("=" * 50)
    
    # Check database
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Run 'python ingest.py' first to ingest PDFs.")
        return
    
    agent = FinancialAgent()
    companies = agent.list_companies()
    print(f"Loaded {len(companies)} companies: {', '.join(c['name'][:20] for c in companies)}")
    print("\nCommands: 'quit' to exit, 'reset' to clear context")
    print("-" * 50)
    
    while True:
        try:
            q = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if not q:
            continue
        if q.lower() in ('quit', 'exit', 'q'):
            break
        if q.lower() == 'reset':
            agent.reset()
            print("Context cleared.")
            continue
        
        try:
            answer = agent.ask(q)
            print(f"\nAgent: {answer}")
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
