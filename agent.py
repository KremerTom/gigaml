#!/usr/bin/env python3
"""Financial Research Agent - Multi-turn conversational AI with semantic search."""
import sqlite3
import json
from openai import OpenAI
from dotenv import load_dotenv
import os
import chromadb
from chromadb.utils import embedding_functions

load_dotenv()

DB_PATH = "data/database/financial_data.db"
VECTORDB_PATH = "data/vectordb"


class FinancialAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.conversation = []
        self.tools = self._define_tools()
        
        # ChromaDB for semantic search
        if os.path.exists(VECTORDB_PATH):
            self.chroma = chromadb.PersistentClient(path=VECTORDB_PATH)
            openai_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.getenv("OPENAI_API_KEY"),
                model_name="text-embedding-3-small"
            )
            self.qualitative_collection = self.chroma.get_or_create_collection(
                name="qualitative",
                embedding_function=openai_ef
            )
        else:
            self.qualitative_collection = None
            
        self.system_prompt = """You are a financial research assistant with access ONLY to a specific corpus of Indian equity research PDFs.

STRICT RULES:
1. ONLY use data returned by your tools. NEVER use external knowledge.
2. If a company is NOT found, say: "I don't have [company] in my corpus."
3. If data is missing, say: "I don't have [specific data] for [company]."
4. ALWAYS cite your source tool.

TOOLS:
- semantic_search: For ANY qualitative questions (business descriptions, mergers, acquisitions, risks, strategy, industry, etc.)
- get_company_metrics: For quantitative data (prices, ratios, forecasts, shareholding)
- get_time_series: For historical financials (P&L, Balance Sheet, Cash Flow, Ratios by period)
- compare_companies: Compare a metric across all companies
- query_database: Custom SQL on tables: companies, metrics, time_series, qualitative

CRITICAL FOR SEMANTIC SEARCH:
- Report ALL potentially relevant matches, not just the top result
- ALSO mention companies in RELATED/ADJACENT industries (e.g., if asked about "metals", also mention cement, mining, industrial companies)
- Structure your answer as:
  1. Direct matches: companies directly in the requested industry
  2. Related industries: companies in adjacent sectors that may be relevant
- When in doubt, INCLUDE the company and explain why it might be relevant
- Read EVERY result returned - don't filter based on narrow interpretation"""

    def _define_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "semantic_search",
                    "description": "Search qualitative content (business descriptions, mergers, acquisitions, risks, strategy). Use for ANY non-numeric questions about companies.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Natural language question or topic"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_metrics",
                    "description": "Get quantitative metrics for a company: prices, market cap, ratios, forecasts, shareholding",
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
                    "description": "Get financial statement time series: P&L, Balance Sheet, Cash Flow, Ratios",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "table_name": {"type": "string", "enum": ["annual_pnl", "quarterly_pnl", "balance_sheet", "cash_flow", "ratios"], "description": "Financial statement type"}
                        },
                        "required": ["company_name", "table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_companies",
                    "description": "Compare a specific metric across all companies in corpus",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric_name": {"type": "string", "description": "Metric to compare (e.g., 'market_cap', 'target_price', 'pe_ratio')"},
                            "sort_order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort order"}
                        },
                        "required": ["metric_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_database",
                    "description": "Run custom SQL query. Tables: companies (name, sector), metrics (field_name, value, unit), time_series (table_name, metric, period, value), qualitative (chunk_type, content)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "SQL SELECT query"}
                        },
                        "required": ["sql"]
                    }
                }
            }
        ]

    # Tool implementations
    def semantic_search(self, query: str):
        """Semantic search using ChromaDB vector embeddings."""
        if not self.qualitative_collection:
            return {"error": "Vector database not available. Run ingestion first."}
        
        try:
            results = self.qualitative_collection.query(
                query_texts=[query],
                n_results=10
            )
            
            if not results["documents"] or not results["documents"][0]:
                return {"matches": [], "note": "No matches found"}
            
            matches = []
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                matches.append({
                    "company": metadata.get("company", "unknown"),
                    "content": doc,
                    "relevance": f"{1 - distance:.2f}" if distance else "?"
                })
            
            return {
                "query": query,
                "matches": matches,
                "note": "READ the content above to find your answer"
            }
        except Exception as e:
            return {"error": str(e)}

    def get_company_metrics(self, company_name: str):
        company = self.db.execute(
            "SELECT id, name, sector FROM companies WHERE name LIKE ?", 
            (f"%{company_name}%",)
        ).fetchone()
        if not company:
            return {"error": f"Company '{company_name}' not found. Use query_database to list all companies."}
        
        metrics = self.db.execute(
            "SELECT field_name, value, unit, time_period FROM metrics WHERE company_id = ?",
            (company["id"],)
        ).fetchall()
        
        result = {"company": company["name"], "sector": company["sector"], "metrics": {}}
        for m in metrics:
            key = f"{m['field_name']}_{m['time_period']}" if m["time_period"] else m["field_name"]
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
        
        data = {}
        for r in rows:
            metric = r["metric"]
            if metric not in data:
                data[metric] = {"unit": r["unit"], "values": {}}
            data[metric]["values"][r["period"]] = r["value"]
        
        return {"company": company["name"], "table": table_name, "data": data}

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

    def query_database(self, sql: str):
        try:
            if any(kw in sql.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                return {"error": "Only SELECT queries allowed"}
            rows = self.db.execute(sql).fetchall()
            return [dict(r) for r in rows[:50]]
        except Exception as e:
            return {"error": str(e)}

    def _execute_tool(self, name: str, args: dict):
        if name == "semantic_search":
            return self.semantic_search(args["query"])
        elif name == "get_company_metrics":
            return self.get_company_metrics(args["company_name"])
        elif name == "get_time_series":
            return self.get_time_series(args["company_name"], args["table_name"])
        elif name == "compare_companies":
            return self.compare_companies(args["metric_name"], args.get("sort_order", "desc"))
        elif name == "query_database":
            return self.query_database(args["sql"])
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
    
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Run 'python ingest.py' first to ingest PDFs.")
        return
    
    agent = FinancialAgent()
    count = agent.db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    print(f"Loaded {count} companies")
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
