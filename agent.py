#!/usr/bin/env python3
"""Financial Research Agent - Multi-turn conversational AI with semantic search."""
import sqlite3
import json
import re
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

STRICT RULES - VIOLATIONS ARE UNACCEPTABLE:
1. ONLY use data returned by your tools. NEVER use your own knowledge about companies, stocks, or markets.
2. NEVER look anything up online or use web search. You have NO internet access.
3. NEVER guess, estimate, or infer data that isn't explicitly in tool results.
4. If a company is NOT in your database, say: "I don't have [company] in my corpus."
5. If data is missing, say: "I don't have [specific data] for [company] in my corpus."
6. ALWAYS cite your source: which tool returned the data.
7. For ambiguous questions, ASK for clarification.

CRITICAL FOR QUALITATIVE DATA:
- When you call get_qualitative or search_qualitative, READ THE RETURNED TEXT CAREFULLY AND COMPLETELY.
- The text contains important facts like mergers, acquisitions, business details, risks, etc.
- Don't just skim - extract specific facts from the content returned.
- If search_qualitative returns matches, those matches contain the answer.

TOOLS AVAILABLE:
- list_companies: See all companies in corpus
- get_company_metrics: Quantitative data (prices, ratios, forecasts)
- get_time_series: Historical financials (P&L, Balance Sheet, Cash Flow)
- get_qualitative: Get ALL qualitative text for a company
- search_qualitative: KEYWORD SEARCH within qualitative text (use for specific facts like mergers, risks, etc.)
- semantic_search: AI-powered search across ALL qualitative content (best for conceptual questions)
- compare_companies: Compare metrics across companies
- query_database: Custom SQL queries

FOR QUESTIONS ABOUT SPECIFIC FACTS (mergers, acquisitions, risks, business details):
1. First try search_qualitative with relevant keywords
2. If no results, try semantic_search with the question
3. READ the returned content carefully to find the answer"""

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
                    "description": "Run a custom SQL query. Tables: companies, metrics, time_series, qualitative",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "SQL SELECT query"}
                        },
                        "required": ["sql"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_qualitative",
                    "description": "Get ALL qualitative text (business highlights, analysis) for a company. Returns full text - read it carefully.",
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
                    "name": "search_qualitative",
                    "description": "KEYWORD SEARCH within qualitative text. Use for specific facts like mergers, acquisitions, risks. Returns matching sentences.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name (optional - omit to search all)"},
                            "keywords": {"type": "string", "description": "Keywords to search for (e.g., 'merger', 'Allahabad', 'risk')"}
                        },
                        "required": ["keywords"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "semantic_search",
                    "description": "AI-powered semantic search across ALL qualitative content. Best for conceptual questions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Natural language question or topic to search for"}
                        },
                        "required": ["query"]
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
                            "metric_name": {"type": "string", "description": "Metric to compare"},
                            "sort_order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort order"}
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
        company = self.db.execute(
            "SELECT id, name, sector FROM companies WHERE name LIKE ?", 
            (f"%{company_name}%",)
        ).fetchone()
        if not company:
            return {"error": f"Company '{company_name}' not found"}
        
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

    def query_database(self, sql: str):
        try:
            if any(kw in sql.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                return {"error": "Only SELECT queries allowed"}
            rows = self.db.execute(sql).fetchall()
            return [dict(r) for r in rows[:50]]
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
            "sections": [{"type": r["chunk_type"], "content": r["content"], "page": r["page_num"]} for r in rows],
            "note": "READ THE CONTENT ABOVE CAREFULLY - it contains important facts about the company"
        }

    def search_qualitative(self, keywords: str, company_name: str = None):
        """Search qualitative text for keywords."""
        # Build query
        if company_name:
            company = self.db.execute(
                "SELECT id, name FROM companies WHERE name LIKE ?",
                (f"%{company_name}%",)
            ).fetchone()
            if not company:
                return {"error": f"Company '{company_name}' not found"}
            rows = self.db.execute(
                "SELECT c.name as company, q.chunk_type, q.content FROM qualitative q JOIN companies c ON q.company_id = c.id WHERE q.company_id = ?",
                (company["id"],)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT c.name as company, q.chunk_type, q.content FROM qualitative q JOIN companies c ON q.company_id = c.id"
            ).fetchall()
        
        # Search for keywords in content
        keywords_list = [k.strip().lower() for k in keywords.split(",")]
        matches = []
        
        for row in rows:
            content = row["content"] or ""
            content_lower = content.lower()
            
            # Check if any keyword matches
            for kw in keywords_list:
                if kw in content_lower:
                    # Extract sentences containing the keyword
                    sentences = re.split(r'[.!?]', content)
                    for sentence in sentences:
                        if kw in sentence.lower():
                            matches.append({
                                "company": row["company"],
                                "type": row["chunk_type"],
                                "match": sentence.strip(),
                                "keyword": kw
                            })
        
        if not matches:
            return {"matches": [], "note": f"No matches found for keywords: {keywords}"}
        
        return {
            "matches": matches[:20],  # Limit results
            "note": "READ THESE MATCHES - they contain the information you're looking for"
        }

    def semantic_search(self, query: str):
        """Semantic search using ChromaDB vector embeddings."""
        if not self.qualitative_collection:
            return {"error": "Vector database not available. Run ingestion first."}
        
        try:
            # Query ChromaDB - it handles embedding automatically
            results = self.qualitative_collection.query(
                query_texts=[query],
                n_results=5
            )
            
            if not results["documents"] or not results["documents"][0]:
                return {"matches": [], "note": "No semantic matches found"}
            
            matches = []
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                matches.append({
                    "company": metadata.get("company", "unknown"),
                    "type": metadata.get("type", "unknown"),
                    "page": metadata.get("page", "?"),
                    "content": doc[:1000],  # Limit for display
                    "relevance": f"{1 - distance:.2f}" if distance else "?"
                })
            
            return {
                "query": query,
                "matches": matches,
                "note": "READ THESE MATCHES CAREFULLY - they contain semantically relevant information"
            }
        except Exception as e:
            return {"error": str(e)}

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
        metrics = self.db.execute("SELECT DISTINCT field_name FROM metrics ORDER BY field_name").fetchall()
        ts_tables = self.db.execute("SELECT DISTINCT table_name FROM time_series").fetchall()
        ts_metrics = self.db.execute("SELECT DISTINCT metric FROM time_series ORDER BY metric").fetchall()
        
        return {
            "tables": ["companies", "metrics", "time_series", "qualitative"],
            "metric_fields": [r[0] for r in metrics],
            "time_series_tables": [r[0] for r in ts_tables],
            "time_series_metrics": [r[0] for r in ts_metrics][:30]
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
        elif name == "search_qualitative":
            return self.search_qualitative(args["keywords"], args.get("company_name"))
        elif name == "semantic_search":
            return self.semantic_search(args["query"])
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
    
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Run 'python ingest.py' first to ingest PDFs.")
        return
    
    agent = FinancialAgent()
    companies = agent.list_companies()
    print(f"Loaded {len(companies)} companies")
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
