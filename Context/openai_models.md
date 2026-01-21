# OpenAI Models Reference - January 2026

**Last Updated:** January 21, 2026

## Selected Model for This Project: GPT-5

### GPT-5 (Our Model)
**API Model ID:** `gpt-5`

GPT-5 is a solid foundation model with multimodal capabilities that we're using for all tasks in this project.

#### Key Features

**Multimodal Capabilities:** GPT-5 has native vision and text understanding - no separate "vision" model needed.

**Vision Capabilities:**
- Strong chart and table understanding for financial documents
- Can interpret dashboards, product screenshots, technical diagrams
- Enhanced spatial understanding of document layout
- Excellent for PDF page analysis

**Reasoning:**
- Good reasoning for complex financial queries
- Supports structured thinking about multi-step problems

#### Function Calling (Tools)

**GPT-5 supports function calling** (also called "tools" in the API), allowing the model to:
- Call external functions/APIs with structured arguments
- Receive structured results back
- Chain multiple function calls together
- Make decisions about which tools to use based on user queries

**Use cases for this project:**
- Database queries (GPT-5 calls a `query_database` function instead of generating SQL as text)
- Vector store searches (GPT-5 calls `search_documents` function)
- Structured data retrieval with validation
- Multi-step queries requiring multiple tool calls

**Benefits:**
- More reliable than text-based outputs
- Built-in input/output validation via JSON schemas
- Better error handling
- Easier to debug and log

#### Structured Outputs

**GPT-5 supports structured outputs** via `response_format` parameter:
- Guarantee JSON schema compliance
- Use Pydantic models to define output structure
- Perfect for data extraction from PDFs
- No parsing errors or malformed JSON

#### Pricing (as of January 2026)

- **Input tokens:** ~$1.50-2.00 per 1M tokens (varies)
- **Output tokens:** ~$10-15 per 1M tokens (varies)
- **Cached inputs:** Significant discount on cached input tokens

## Why GPT-5 for This Project

For the Financial Research AI Agent, we are using **`gpt-5`** for all tasks:

**Vision + Data Extraction:**
- Native vision capabilities for analyzing PDF images
- Strong chart/table understanding
- Structured outputs support

**Text Processing & Schema Evolution:**
- Excellent text understanding
- Can identify synonyms and field relationships
- Consistent performance

**Query Workflow (Runtime):**
- Good reasoning for complex financial queries
- Multimodal capabilities for hybrid queries
- Function calling support for tool use

**Why GPT-5?**
- Proven stability and reliability
- Cost-effective for high-volume processing
- Sufficient capabilities for equity research document analysis
- Native multimodal support (no separate vision model needed)
- Can upgrade to newer models later if needed

## Newer Models Available (Not Currently Used)

### GPT-5.2 Family
**Released:** December 2025

OpenAI's newest flagship models with enhanced capabilities:
- **`gpt-5.2`** - Main model with thinking capabilities
- **`gpt-5.2-chat-latest`** - Instant variant (faster responses)
- **`gpt-5.2-pro`** - Pro variant (more compute for harder problems)

**New features in 5.2:**
- Enhanced reasoning with `xhigh` reasoning level
- Improved vision capabilities
- Better chart and dashboard analysis
- Context compaction features

**Why not using it yet:**
- GPT-5 is sufficient for our needs
- Want proven stability before upgrading
- Can migrate later if needed

### Other Specialized Models
- **GPT-5.2-Codex** - Optimized for coding tasks
- **o3-mini** - Small reasoning model for science/math/coding

## API Documentation

- **Official Docs:** https://platform.openai.com/docs/models/
- **GPT-5 Docs:** https://platform.openai.com/docs/models/gpt-5
- **Usage Guide:** https://platform.openai.com/docs/guides/
- **Changelog:** https://platform.openai.com/docs/changelog

## Notes

- GPT-5 supports **multimodal input** (text + images)
- No separate "vision" model needed - vision is built into GPT-5
- Supports **structured outputs** via `response_format` parameter
- Supports **function calling** (tools) for structured data retrieval
- **Context window:** Large (likely 128K+ tokens)
- Available immediately to API users
