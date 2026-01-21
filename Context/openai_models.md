# OpenAI Models Reference - January 2026

**Last Updated:** January 21, 2026

## Current Models

### GPT-5.2 (Latest Flagship Model)
**Released:** December 2025

GPT-5.2 is OpenAI's flagship model for coding and agentic tasks across industries, replacing GPT-5.1.

#### API Model IDs

- **`gpt-5.2`** - Main model (GPT-5.2 Thinking variant)
- **`gpt-5.2-chat-latest`** - GPT-5.2 Instant variant (powering ChatGPT)
- **`gpt-5.2-pro`** - GPT-5.2 Pro variant (uses more compute for harder problems)

#### Model Variants

1. **GPT-5.2 Instant** (`gpt-5.2-chat-latest`)
   - Fast responses for real-time applications
   - Optimized for chat interactions

2. **GPT-5.2 Thinking** (`gpt-5.2`)
   - Deep reasoning capabilities
   - Supports reasoning.effort levels: none (default), low, medium, high, xhigh
   - New in 5.2: xhigh reasoning level, concise reasoning summaries

3. **GPT-5.2 Pro** (`gpt-5.2-pro`)
   - Highest performance tier
   - Uses more compute to provide consistently better answers

#### Vision Capabilities

**GPT-5.2 has native multimodal capabilities** - no separate "vision" model needed.

Key vision features:
- **Strongest vision model yet** - error rates cut roughly in half on chart reasoning and software interface understanding
- **Enhanced spatial understanding** - stronger grasp of how elements are positioned within images
- **Chart and dashboard analysis** - accurately interprets dashboards, product screenshots, technical diagrams, visual reports
- **GUI understanding** - 86.3% accuracy on ScreenSpot-Pro benchmark (up from 64.2% in GPT-5.1)
- **Stronger vision + text fusion** - better integration of visual and textual information

#### Reasoning Features

- **reasoning.effort** parameter supports: `none`, `low`, `medium`, `high`, `xhigh`
- **Context management** - new compaction features for long conversations
- **Client-side compaction** - `/responses/compact` endpoint to shrink context in long-running conversations

#### Function Calling (Tools)

GPT-5 supports **function calling** (also called "tools" in the API), allowing the model to:
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

GPT-5 supports **structured outputs** via `response_format` parameter:
- Guarantee JSON schema compliance
- Use Pydantic models to define output structure
- Perfect for data extraction from PDFs
- No parsing errors or malformed JSON

#### Pricing (as of January 2026)

- **Input tokens:** $1.75 per 1M tokens
- **Output tokens:** $14 per 1M tokens
- **Cached inputs:** 90% discount on cached input tokens

## Specialized Models

### GPT-5.2-Codex
**Released:** January 2026 (now default for Codex API)

- Version of GPT-5.2 optimized for agentic coding tasks
- Enhanced code understanding and generation
- Better screenshot and technical diagram interpretation

### GPT-5.1-Codex-max
**Released:** January 2026

- Most intelligent coding model
- Optimized for long-horizon, agentic coding tasks
- Available via Responses API

### o3-mini
**Released:** January 2026

- Small reasoning model
- Optimized for science, math, and coding tasks
- More cost-effective for specific use cases

## GPT-5 (Base Model)

**API Model ID:** `gpt-5`

- Solid foundation model with multimodal capabilities
- Supports text and vision inputs
- Available and actively supported
- Good balance of performance and cost

## Deprecated Models

- **GPT-4 family** - Still available but superseded by GPT-5 family

## For This Project

### Selected Model: GPT-5

For the Financial Research AI Agent, we are using **`gpt-5`** for all tasks:

1. **Vision + Data Extraction:** `gpt-5`
   - Native vision capabilities for analyzing PDF images
   - Strong chart/table understanding
   - Structured outputs support

2. **Text Processing & Schema Evolution:** `gpt-5`
   - Same model for consistency
   - No need for separate text model

3. **Query Workflow (Runtime):** `gpt-5`
   - Good reasoning for complex financial queries
   - Multimodal capabilities for hybrid queries

**Why GPT-5 (not 5.2 or Pro)?**
- Proven stability and reliability
- Cost-effective for high-volume processing
- Sufficient capabilities for equity research document analysis
- Can upgrade to newer models later if needed

## API Documentation

- **Official Docs:** https://platform.openai.com/docs/models/
- **GPT-5.2 Docs:** https://platform.openai.com/docs/models/gpt-5.2
- **Usage Guide:** https://platform.openai.com/docs/guides/latest-model
- **Changelog:** https://platform.openai.com/docs/changelog

## Notes

- All GPT-5.2 variants support **multimodal input** (text + images)
- No separate "vision" model exists - vision is built into GPT-5.2
- Models support **structured outputs** via `response_format` parameter
- **Context window:** Documentation doesn't specify, but likely 128K+ tokens
- All models available immediately to API users as of January 2026
