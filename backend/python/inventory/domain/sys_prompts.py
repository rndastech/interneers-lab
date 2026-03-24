GENERATE_PRODUCTS_PROMPT = """You are a helpful assistant that generates synthetic product data for inventory systems.
Generate {quantity} unique synthetic products.
{category_prompt}
{special_instructions}

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

SPECIAL_INSTRUCTIONS_DEFAULT = "- Generate realistic, varied products with moderate stock levels."

SCENARIO_HOLIDAY_RUSH = "- Generate seasonal holiday products. Prices should be mid to premium. Stock levels should be HIGH (800-2000 units). Brands should be festive/celebratory themed."

SCENARIO_FLASH_SALE = "- Generate popular, fast-moving consumer products. Prices should be budget to mid-range. Stock levels should be MODERATE to HIGH (200-1000 units). Focus on items that appeal to bargain hunters."

SCENARIO_BACK_TO_SCHOOL = "- Generate school and education-related products. Prices should range from budget to mid-range. Stock levels should be HIGH (100-1500 units). Include both basic supplies and tech items."

SCENARIO_PREMIUM_ELECTRONICS = "- Generate high-end, premium electronics and tech products. Prices should be PREMIUM (high pricing $500+). Stock levels should be LOW (5-50 units reflecting high-value inventory). Brand names should be prestigious."

SCENARIO_WAREHOUSE_OVERSTOCK = "- Generate a diverse mix of everyday consumer products across all categories. Prices should be LOW to MID-RANGE. Stock levels should be VERY HIGH (1000-5000+ units). Create a realistic overstock scenario with bulk quantities."