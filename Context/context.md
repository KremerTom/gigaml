# Financial Research AI Agent - Project Context

## Coding assistant behavior
Keep responses brief. Put all test files in a tmp folder, and whenever I give you a compliment, clear the tmp folder and make any relevant updates to the context files.

## Project Overview
Building a multi-turn conversational AI agent that answers financial research questions using a corpus of equity research PDFs from Geojit (Indian investment service provider). This mimics how a human research analyst would retrieve and analyze information.

**Data Source:** 20 equity research PDFs (scalable architecture for 20,000+ documents)
**Interface:** Python CLI (no UI, no persistent sessions required)
**Deployment:** Local-only (no cloud services)
**Primary Model:** OpenAI GPT-5 (multimodal - text and vision)

## Critical Requirements

### Accuracy (Highest Priority)
- Answers must be grounded ONLY in the provided PDFs
- No web search or external data sources
- If data is missing/ambiguous, explicitly say so instead of guessing
- If a company is not in the corpus, refuse to answer about it
- High bar for precision over recall

### Performance
- Response time: seconds (not minutes)
- Unlimited token usage allowed
- Must scale architecturally to thousands of PDFs

### Functionality
- Multi-turn conversations with context retention ("that company", "last quarter", etc.)
- Support three question types:
  1. **Specific company queries:** "What is the market cap of XYZ?"
  2. **Grouping queries:** "What companies are in banking?"
  3. **Complex aggregations:** "Top 5 companies by market cap, sorted by tax for FY25"

### Example Questions to Support
- "How much profit did Company X make last quarter?"
- "What was the EBITDA margin for Company X last year?"
- "Which company in Sector Y had the highest total assets growth in 2020?"
- "Rank these companies by revenue growth over the last 3 years."
- "Why did sales drop last quarter for Company X?" (qualitative)
- "What key risks are mentioned for Company X?" (qualitative)

## Data Extraction Scope

### In Scope
- Tables (structured financial data)
- Text (qualitative analysis, headers, industry descriptions)
- Ticker symbols
- Headers and metadata

### Out of Scope
- Charts and visual graphics (skip chart interpretation, extract surrounding text only)
- Disclaimer pages (ignore, assume identical across PDFs)
- Images within PDFs that are decorative or logos

## Architecture Design

### Data Ingestion Pipeline (Async, Run Ahead of Time)
1. **Schema Generation**
   - Convert PDF pages to images (pdf2image)
   - Send to GPT-5: "What fields exist in this document?"

2. **Schema Evolution**
   - Send new fields + existing schema to GPT-5: "Which are synonyms? Which are new?"
   - Build synonym mappings for field name variations across PDFs
   - Dynamically update schema (no hardcoding metrics)

3. **Data Extraction**
   - Send pages to GPT-5 with current schema
   - Extract structured data using OpenAI Structured Outputs

4. **Storage**
   - Quantitative data → SQLite (local, built-in Python)
   - Qualitative data → OpenAI hosted vector store (Files API + file_search tool)

5. **Data Clearing**
   - Support for wiping tables/vector store for fresh starts

### Agent Query Workflow (Runtime)

**Uses OpenAI Function Calling (Tools) for structured data retrieval**

1. **Question Classification**
   - GPT-5 determines: quantitative, qualitative, or hybrid
   - Uses conversation context for multi-turn queries

2. **Function Calling Tools Available to GPT-5:**
   - `query_database()` - Execute SQL queries against SQLite
   - `search_documents()` - Semantic search in vector store (file_search tool)
   - `get_schema()` - Retrieve current schema and field mappings
   - `get_company_list()` - List all companies in corpus
   - `get_field_values()` - Get specific field values for a company

3. **Query Execution Flow**
   - GPT-5 receives user question + available tools
   - GPT-5 decides which tool(s) to call based on question type
   - Tools execute and return structured data
   - GPT-5 synthesizes answer from tool results
   - Includes sources (SQL queries, document references) for transparency

4. **Multi-Turn Context**
   - Conversation history maintained within session
   - GPT-5 resolves references ("that company", "last quarter")
   - Function calls can reference previous results

## Technology Stack

- **PDF Processing:** pdf2image
- **AI/ML:** OpenAI API (GPT-5 multimodal, Structured Outputs)
- **Database:** sqlite3 (local, no installation)
- **Vector Store:** OpenAI hosted vector store (Files API + file_search)
- **Language:** Python
- **CLI Framework:** (to be determined)

## Design Constraints

### Must NOT Use
- Cloud deployment services
- Turnkey solutions (e.g., Reducto) that trivialize the problem
- Pre-built financial agents

### Must Design For
- **Scalability:** Architecture should work with 100-20,000 PDFs
- **Flexibility:** Handle PDF variations (different table structures, field name variations)
- **Dynamic Schema:** No hardcoded metrics, support 100+ different fields
- **Latency Optimization:** Sub-minute responses (consider voice agent use case)

## Deliverables

1. Git repository with all code
2. GitHub public link
3. Demo video showing multi-turn conversation interaction
4. Separation between ingestion and chat components
5. CLI interface for starting/running chat sessions

## Session Management
- Each CLI session is independent
- No persistent chat history across sessions
- Multi-turn context maintained within a single session
- Clean slate on new session start