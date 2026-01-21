#!/usr/bin/env python3
"""Test suite for Financial Research Agent."""
import random
from agent import FinancialAgent

# Question bank
QUESTIONS = [
    # Basic queries
    ("List all companies", "list_companies"),
    ("What is the target price for Hindalco?", "single_metric"),
    ("What sector is Grasim in?", "company_info"),
    ("Compare market cap of all companies", "compare"),
    ("Which company has the highest target price?", "ranking"),
    ("What are the business highlights for Hindalco?", "qualitative"),
    ("What metrics do you have available?", "schema"),
    
    # Critical rules tests
    ("What is the revenue for Apple Inc?", "rule_unknown_company"),  # Should refuse
    ("Tell me about Tesla's market cap", "rule_refuse_unknown"),  # Should refuse
    ("What is Hindalco's EBITDA for FY24?", "rule_cite_sources"),  # Should cite source
    ("What is the CEO's salary at Grasim?", "rule_missing_data"),  # Should say not available
    ("What was the growth?", "rule_ambiguous"),  # Should ask for clarification
]

def test_agent():
    print("=" * 50)
    print("Financial Agent Test (3 Random Questions)")
    print("=" * 50)
    
    agent = FinancialAgent()
    companies = agent.list_companies()
    print(f"Loaded {len(companies)} companies")
    
    # Pick 3 random questions
    selected = random.sample(QUESTIONS, 3)
    
    for question, test_type in selected:
        print(f"\n[{test_type}] Q: {question}")
        print("-" * 40)
        try:
            answer = agent.ask(question)
            print(f"A: {answer[:400]}..." if len(answer) > 400 else f"A: {answer}")
        except Exception as e:
            print(f"ERROR: {e}")
        agent.reset()
    
    print("\n" + "=" * 50)
    print("Done")
    print("=" * 50)


if __name__ == "__main__":
    test_agent()
