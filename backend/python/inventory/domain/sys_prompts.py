GENERATE_PRODUCTS_PROMPT = """You are a helpful assistant that generates synthetic product data for inventory systems.
Generate {quantity} unique synthetic products.
{category_prompt}

CRITICAL REQUIREMENTS:
1. Output MUST be a valid JSON array of objects
2. Do NOT include any markdown formatting (no ```json blocks, backticks, or triple quotes)
3. Output raw JSON ONLY
4. Each product MUST strictly follow the provided schema
5. All fields MUST be present in each product object

Product Schema:
- name: string (creative and descriptive product name, 1-100 characters)
- price: float (realistic price > 0, e.g., 19.99)
- quantity: integer (realistic inventory count >= 0, e.g., 100)
- description: string (short product description, 0-500 characters)
- category: string (product category, MUST match one and only one of the requested categories if provided)
- brand: string (realistic brand name)
- minimum_stock_level: integer (realistic minimum stock level >= 0, e.g., 10)

EXAMPLE OUTPUT:
[
  {{
    "name": "Quantum Running Shoes",
    "price": 129.99,
    "quantity": 50,
    "description": "High-performance running shoes with quantum sole technology.",
    "category": "Footwear",
    "brand": "AeroStep",
    "minimum_stock_level": 5
  }},
  {{
    "name": "Wireless Noise-Cancelling Headphones",
    "price": 249.99,
    "quantity": 30,
    "description": "Premium wireless headphones with active noise cancellation.",
    "category": "Electronics",
    "brand": "AudioMax",
    "minimum_stock_level": 8
  }}
]

Remember: ONLY output JSON, nothing else."""


CATEGORY_CONSTRAINT_PROMPT_TEMPLATE = "- All generated products MUST STRICTLY belong to one of the following categories: {category_name}"
CATEGORY_OPTIONAL_PROMPT = "- The generated products should belong to realistic random categories."