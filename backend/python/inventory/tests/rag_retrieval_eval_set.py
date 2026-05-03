RAG_RETRIEVAL_EVAL_SET = [
    {
        "query": "What's the return policy for damaged items?",
        "expected_source_ids": ["return_policy"],
        "expected_phrases": ["damaged", "refund", "replacement", "return shipping"],
        "include_product_context": False,
    },
    {
        "query": "Who pays return shipping if an item arrives damaged?",
        "expected_source_ids": ["return_policy"],
        "expected_phrases": ["return shipping", "covered"],
        "include_product_context": False,
    },
    {
        "query": "What warranty duration applies to premium electronics?",
        "expected_source_ids": ["product_manual"],
        "expected_phrases": ["24", "warranty"],
        "include_product_context": False,
    },
    {
        "query": "What information must vendors provide for each product?",
        "expected_source_ids": ["vendor_faq"],
        "expected_phrases": ["title", "category", "brand", "warranty", "support"],
        "include_product_context": False,
    },
    {
        "query": "How quickly must vendors acknowledge defect reports?",
        "expected_source_ids": ["vendor_faq"],
        "expected_phrases": ["2 business days", "defect"],
        "include_product_context": False,
    },
]

MANDATORY_RETURN_POLICY_QUERY = "What's the return policy for damaged items?"
