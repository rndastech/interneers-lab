RAG_QA_EVAL_SET = [
    {
        "query": "What's the return policy for damaged items?",
        "expected_source_ids": ["return_policy"],
        "expected_keywords": ["damaged", "7", "refund", "replacement", "shipping"],
        "min_keyword_coverage": 0.30,
        "include_product_context": False,
    },
    {
        "query": "How long is the warranty for premium electronics?",
        "expected_source_ids": ["product_manual"],
        "expected_keywords": ["24", "warranty", "premium"],
        "min_keyword_coverage": 0.25,
        "include_product_context": False,
    },
    {
        "query": "What data should vendors provide for each product?",
        "expected_source_ids": ["vendor_faq"],
        "expected_keywords": ["title", "category", "brand", "warranty", "support"],
        "min_keyword_coverage": 0.30,
        "include_product_context": False,
    },
    {
        "query": "What should I do if replacement stock is unavailable?",
        "expected_source_ids": ["return_policy"],
        "expected_keywords": ["replacement", "unavailable", "refund"],
        "min_keyword_coverage": 0.25,
        "include_product_context": False,
    },
]
