import io
import pandas as pd
import requests
import streamlit as st
from typing import Optional

BASE_URL = "http://localhost:8000/inventory"
PRODUCTS_URL = f"{BASE_URL}/products/"
PRODUCTS_CSV_URL = f"{BASE_URL}/products/csv/"
CATEGORIES_URL = f"{BASE_URL}/categories/"
SIMILAR_PRODUCTS_URL = f"{BASE_URL}/products/similar/"

DISPLAY_COLUMNS = [
    "id", "name", "brand", "category", "barcode",
    "price", "quantity", "minimum_stock_level",
    "description", "created_at", "updated_at",
]

MIME_CSV = "text/csv"
MSG_NO_CONNECTION = (
    "Cannot connect to the API"
)
MSG_ROW_ERRORS = "Row errors:"
LABEL_ERRORS = "Errors"
LABEL_FILE_UPLOADER = "Choose CSV file"

NAV_LIST = "Product List"
NAV_CREATE = "Create Product"
NAV_UPDATE = "Update Product"
NAV_DELETE = "Delete Product"
NAV_CSV = "CSV Bulk Operations"
NAV_SCENARIOS = "Scenario Selector"

st.set_page_config(page_title="Inventory Dashboard", layout="wide")


@st.cache_data(ttl=30)
def fetch_all_products() -> list:
    products = []
    url = PRODUCTS_URL + "?page_size=100"
    while url:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            products.extend(data.get("results", []))
            url = data.get("next")
        except requests.exceptions.ConnectionError:
            st.error(MSG_NO_CONNECTION)
            return []
        except requests.exceptions.HTTPError as exc:
            st.error(f"API error: {exc}")
            return []
    return products


@st.cache_data(ttl=60)
def fetch_categories() -> list:
    categories = []
    url = CATEGORIES_URL + "?page_size=100"
    while url:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            categories.extend(c["title"] for c in data.get("results", []))
            url = data.get("next")
        except requests.exceptions.ConnectionError:
            st.error(MSG_NO_CONNECTION)
            return []
        except requests.exceptions.HTTPError as exc:
            st.error(f"API error: {exc}")
            return []
    return categories


def fetch_similar_products(query: Optional[str] = None, product_id: Optional[str] = None, top_k: int = 10) -> list:
    try:
        params: dict = {"top_k": top_k}
        
        # Must provide exactly one of query or product_id
        if query is not None and query.strip():
            params["query"] = query
        elif product_id is not None and product_id.strip():
            params["product_id"] = product_id
        else:
            st.error("Please provide either a query or product ID")
            return []
        
        resp = requests.get(
            SIMILAR_PRODUCTS_URL,
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except requests.exceptions.ConnectionError:
        st.error(MSG_NO_CONNECTION)
        return []
    except requests.exceptions.HTTPError as exc:
        try:
            error_detail = exc.response.json().get("error", str(exc))
        except Exception:
            error_detail = str(exc)
        st.error(f"API error: {error_detail}")
        return []
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return []


def show_response(resp: requests.Response, success_code: int, success_msg: str) -> None:
    if resp.status_code == success_code:
        st.success(f"{success_msg}")
    else:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text or f"HTTP {resp.status_code}"
        st.error(f"Error {resp.status_code}: {detail}")


def show_bulk_errors(data: dict) -> None:
    if data.get("errors"):
        st.error(MSG_ROW_ERRORS)
        st.json(data["errors"])


def highlight_low_stock(row: pd.Series) -> list:
    try:
        qty = float(row["quantity"])
        min_lvl = float(row["minimum_stock_level"])
        if qty <= min_lvl:
            return ["background-color: #ffcccc; color: #7a0000"] * len(row)
    except (ValueError, TypeError, KeyError):
        pass
    return [""] * len(row)

st.sidebar.title("Inventory Dashboard")
section = st.sidebar.radio(
    "Navigation",
    [NAV_LIST, NAV_CREATE, NAV_UPDATE, NAV_DELETE, NAV_CSV, NAV_SCENARIOS],
)


if section == NAV_LIST:
    st.title("Product List")

    # Similarity Search Section
    st.subheader("🔍 Find Similar Products")
    sim_search_col1, sim_search_col2 = st.columns([3, 1])
    with sim_search_col1:
        similarity_search = st.text_input("Search by query for similar items", placeholder="Enter product name, description, or query…")
    with sim_search_col2:
        similarity_top_k = st.number_input("Top K results", min_value=1, max_value=50, value=10)
    
    # Display similarity search results if a query is provided
    if similarity_search:
        st.divider()
        st.subheader("Similar Products Results")
        try:
            similar_products = fetch_similar_products(query=similarity_search, top_k=int(similarity_top_k))
            if similar_products:
                similar_df = pd.DataFrame(similar_products)
                for col in DISPLAY_COLUMNS:
                    if col not in similar_df.columns:
                        similar_df[col] = ""
                similar_df = similar_df[[col for col in DISPLAY_COLUMNS if col in similar_df.columns]]
                st.caption(f"Found **{len(similar_df)}** similar product(s)")
                st.dataframe(similar_df, use_container_width=True, hide_index=True)
            else:
                st.info("No similar products found.")
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching similar products: {str(e)}")
        st.divider()

    st.subheader("All Products")
    col_search, col_cat, col_refresh = st.columns([3, 2, 1])
    with col_search:
        search = st.text_input("Search (name / barcode / description)", placeholder="laptop…")
    with col_cat:
        categories = fetch_categories()
        cat_filter = st.multiselect("Filter by category", options=categories)
    with col_refresh:
        st.write("")
        if st.button("Refresh"):
            fetch_all_products.clear()
            fetch_categories.clear()
            st.rerun()

    products = fetch_all_products()

    if products:
        df = pd.DataFrame(products)
        for col in DISPLAY_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[DISPLAY_COLUMNS]

        if search:
            mask = (
                df["name"].str.contains(search, case=False, na=False)
                | (df["barcode"].str.contains(search, case=False, na=False) if "barcode" in df.columns else False)
                | df["description"].str.contains(search, case=False, na=False)
            )
            df = df[mask]

        if cat_filter:
            df = df[df["category"].str.lower().isin([c.lower() for c in cat_filter])]

        st.caption(f"Showing **{len(df)}** product(s)")

        low_stock_count = (
            pd.to_numeric(df["quantity"], errors="coerce")
            <= pd.to_numeric(df["minimum_stock_level"], errors="coerce")
        ).sum()
        if low_stock_count:
            st.warning(f"**{low_stock_count}** product(s) are below their minimum stock level.")

        # Display products with "Find Similar" button
        st.subheader("Product Details")
        for idx, row in df.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**{row['name']}** — {row.get('brand', '')}")
                    st.caption(f"ID: {row['id']} | Category: {row.get('category', 'N/A')} | Price: ${row.get('price', 'N/A')} | Qty: {row.get('quantity', 'N/A')}")
                    if row.get('description'):
                        st.text(row['description'][:100] + ("..." if len(str(row['description'])) > 100 else ""))
                
                with col2:
                    if st.button("🔗 Find Similar", key=f"btn_similar_{row['id']}", use_container_width=True):
                        st.session_state.selected_product_id = row['id']
                        st.session_state.show_similar = True
                        st.rerun()
        
        # Handle similar products display when button is clicked
        if st.session_state.get("show_similar") and st.session_state.get("selected_product_id"):
            st.divider()
            st.subheader(f"🔗 Top 10 Similar Products for ID: {st.session_state['selected_product_id']}")
            
            try:
                similar_products = fetch_similar_products(
                    product_id=st.session_state["selected_product_id"],
                    top_k=10
                )
                if similar_products:
                    similar_df = pd.DataFrame(similar_products)
                    for col in DISPLAY_COLUMNS:
                        if col not in similar_df.columns:
                            similar_df[col] = ""
                    similar_df = similar_df[[col for col in DISPLAY_COLUMNS if col in similar_df.columns]]
                    st.dataframe(similar_df, use_container_width=True, hide_index=True)
                    
                    col_download, col_close = st.columns([1, 1])
                    with col_download:
                        st.download_button(
                            label="Download as CSV",
                            data=similar_df.to_csv(index=False).encode("utf-8"),
                            file_name=f"similar_products_{st.session_state['selected_product_id']}.csv",
                            mime=MIME_CSV,
                        )
                    with col_close:
                        if st.button("Close", use_container_width=True):
                            st.session_state.show_similar = False
                            st.rerun()
                else:
                    st.info("No similar products found for this item.")
                    if st.button("Close"):
                        st.session_state.show_similar = False
                        st.rerun()
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching similar products: {str(e)}")
                if st.button("Close"):
                    st.session_state.show_similar = False
                    st.rerun()

        st.divider()
        st.download_button(
            label="Download current view as CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="products_export.csv",
            mime=MIME_CSV,
        )
    else:
        st.info("No products found.")


elif section == NAV_CREATE:
    st.title(NAV_CREATE)

    categories = fetch_categories()
    cat_options = [""] + categories

    with st.form("create_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name *", placeholder="e.g. Laptop")
        brand = c2.text_input("Brand *", placeholder="e.g. HP")

        c3, c4, c5 = st.columns(3)
        price = c3.number_input("Price *", min_value=0.01, step=0.01, format="%.2f")
        quantity = c4.number_input("Quantity *", min_value=0, step=1)
        min_stock = c5.number_input("Min Stock Level", min_value=0, step=1)

        c6, c7 = st.columns(2)
        barcode = c6.text_input("Barcode", placeholder="e.g. LAP001")
        category = c7.selectbox("Category *", options=cat_options)

        description = st.text_area("Description", placeholder="Optional product description…")
        submitted = st.form_submit_button("Create Product", use_container_width=True)

    if submitted:
        missing = []
        if not name:
            missing.append("Name")
        if not brand:
            missing.append("Brand")
        if not category:
            missing.append("Category")
        if missing:
            st.warning(f"Required field(s) missing: {', '.join(missing)}.")
        else:
            payload = {
                "name": name,
                "price": str(price),
                "quantity": int(quantity),
                "description": description,
                "barcode": barcode,
                "brand": brand,
                "category": category,
                "minimum_stock_level": int(min_stock),
            }
            try:
                resp = requests.post(PRODUCTS_URL, json=payload, timeout=10)
                show_response(resp, 201, f"Product '{name}' created successfully!")
                if resp.status_code == 201:
                    fetch_all_products.clear()
                    st.json(resp.json())
            except requests.exceptions.ConnectionError:
                st.error(MSG_NO_CONNECTION)
elif section == NAV_UPDATE:
    st.title(NAV_UPDATE)

    product_id = st.text_input("Product ID (24-char hex)", placeholder="65f1a2b3c4d5e6f7a8b9c0d1")

    if product_id:
        try:
            get_resp = requests.get(f"{PRODUCTS_URL}{product_id}/", timeout=10)
        except requests.exceptions.ConnectionError:
            st.error(MSG_NO_CONNECTION)
            get_resp = None

        if get_resp and get_resp.status_code == 200:
            product = get_resp.json()
            categories = fetch_categories()
            cat_options = [""] + categories

            st.caption("Current values are pre-filled. Edit only the fields you want to change.")

            with st.form("update_form"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Name", value=product.get("name", ""))
                brand = c2.text_input("Brand", value=product.get("brand", ""))

                c3, c4, c5 = st.columns(3)
                price = c3.number_input(
                    "Price", min_value=0.01, step=0.01, format="%.2f",
                    value=max(0.01, float(product.get("price") or 0.01)),
                )
                quantity = c4.number_input(
                    "Quantity", min_value=0, step=1,
                    value=int(product.get("quantity") or 0),
                )
                min_stock = c5.number_input(
                    "Min Stock Level", min_value=0, step=1,
                    value=int(product.get("minimum_stock_level") or 0),
                )

                c6, c7 = st.columns(2)
                barcode = c6.text_input("Barcode", value=product.get("barcode", ""))
                current_cat = product.get("category", "")
                cat_index = cat_options.index(current_cat) if current_cat in cat_options else 0
                category = c7.selectbox("Category", options=cat_options, index=cat_index)

                description = st.text_area("Description", value=product.get("description", ""))
                submitted = st.form_submit_button("Save Changes", use_container_width=True)

            if submitted:
                payload = {
                    "name": name,
                    "price": str(price),
                    "quantity": int(quantity),
                    "description": description,
                    "barcode": barcode,
                    "brand": brand,
                    "minimum_stock_level": int(min_stock),
                    "category": category,
                }
                try:
                    resp = requests.patch(f"{PRODUCTS_URL}{product_id}/", json=payload, timeout=10)
                    show_response(resp, 200, "Product updated successfully!")
                    if resp.status_code == 200:
                        fetch_all_products.clear()
                        st.json(resp.json())
                except requests.exceptions.ConnectionError:
                    st.error(MSG_NO_CONNECTION)

        elif get_resp:
            st.error(
                f"{get_resp.status_code}: "
                f"{get_resp.json().get('error', 'Product not found.')}"
            )


elif section == NAV_DELETE:
    st.title(NAV_DELETE)

    product_id = st.text_input("Product ID (24-char hex)", placeholder="65f1a2b3c4d5e6f7a8b9c0d1")

    if product_id:
        try:
            preview_resp = requests.get(f"{PRODUCTS_URL}{product_id}/", timeout=10)
        except requests.exceptions.ConnectionError:
            st.error(MSG_NO_CONNECTION)
            preview_resp = None

        if preview_resp and preview_resp.status_code == 200:
            product = preview_resp.json()
            st.info(
                f"**{product['name']}** — {product.get('brand', '')} "
                f"| Price: {product['price']} | Qty: {product['quantity']}"
            )
            if st.checkbox("I confirm I want to delete this product") and st.button(
                "Confirm Delete", type="primary"
            ):
                try:
                    resp = requests.delete(f"{PRODUCTS_URL}{product_id}/", timeout=10)
                    show_response(resp, 204, "Product deleted successfully!")
                    if resp.status_code == 204:
                        fetch_all_products.clear()
                except requests.exceptions.ConnectionError:
                    st.error(MSG_NO_CONNECTION)

        elif preview_resp:
            st.error(
                f"{preview_resp.status_code}: "
                f"{preview_resp.json().get('error', 'Product not found.')}"
            )


elif section == NAV_CSV:
    st.title(NAV_CSV)

    tab_create, tab_update, tab_delete, tab_templates = st.tabs(
        ["Bulk Create", "Bulk Update", "Bulk Delete", "CSV Templates"]
    )

    with tab_create:
        st.subheader("Bulk Create Products from CSV")
        st.markdown(
            "Upload a CSV with columns: `name`, `price`, `quantity`, "
            "`description`, `barcode`, `category`, `brand`, `minimum_stock_level`"
        )
        uploaded = st.file_uploader(LABEL_FILE_UPLOADER, type=["csv"], key="csv_create")
        if uploaded and st.button("Upload & Create", key="btn_csv_create"):
            try:
                resp = requests.post(
                    PRODUCTS_CSV_URL,
                    files={"file": (uploaded.name, uploaded.getvalue(), MIME_CSV)},
                    timeout=30,
                )
                if resp.status_code in (201, 207):
                    data = resp.json()
                    col1, col2 = st.columns(2)
                    col1.metric("Created", data.get("created_count", 0))
                    col2.metric(LABEL_ERRORS, data.get("error_count", 0))
                    if data.get("created"):
                        st.dataframe(pd.DataFrame(data["created"]), use_container_width=True, hide_index=True)
                    show_bulk_errors(data)
                else:
                    st.error(f"{resp.status_code}: {resp.json()}")
            except requests.exceptions.ConnectionError:
                st.error(MSG_NO_CONNECTION)

    with tab_update:
        st.subheader("Bulk Update Products from CSV")
        st.markdown(
            "Upload a CSV with `id` as a required column, plus any fields to update: "
            "`name`, `price`, `quantity`, `description`, `barcode`, `category`, `brand`, `minimum_stock_level`"
        )
        uploaded_upd = st.file_uploader(LABEL_FILE_UPLOADER, type=["csv"], key="csv_update")
        if uploaded_upd and st.button("Upload & Update", key="btn_csv_update"):
            try:
                resp = requests.patch(
                    PRODUCTS_CSV_URL,
                    files={"file": (uploaded_upd.name, uploaded_upd.getvalue(), MIME_CSV)},
                    timeout=30,
                )
                if resp.status_code in (200, 207):
                    data = resp.json()
                    col1, col2 = st.columns(2)
                    col1.metric("Updated", data.get("updated_count", 0))
                    col2.metric(LABEL_ERRORS, data.get("error_count", 0))
                    if data.get("updated"):
                        st.dataframe(pd.DataFrame(data["updated"]), use_container_width=True, hide_index=True)
                    show_bulk_errors(data)
                else:
                    st.error(f"{resp.status_code}: {resp.json()}")
            except requests.exceptions.ConnectionError:
                st.error(MSG_NO_CONNECTION)

    with tab_delete:
        st.subheader("Bulk Delete Products from CSV")
        st.markdown("Upload a CSV with a single column: `id`")
        uploaded_del = st.file_uploader(LABEL_FILE_UPLOADER, type=["csv"], key="csv_delete")
        if uploaded_del:
            preview_df = pd.read_csv(io.BytesIO(uploaded_del.getvalue()))
            st.caption(f"Preview — {len(preview_df)} row(s)")
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
            if st.checkbox("I confirm I want to delete these products", key="confirm_bulk_del") and st.button(
                "Upload & Delete", key="btn_csv_delete"
            ):
                try:
                    resp = requests.delete(
                        PRODUCTS_CSV_URL,
                        files={"file": (uploaded_del.name, uploaded_del.getvalue(), MIME_CSV)},
                        timeout=30,
                    )
                    if resp.status_code in (200, 207):
                        data = resp.json()
                        col1, col2 = st.columns(2)
                        col1.metric("Deleted", data.get("deleted_count", 0))
                        col2.metric(LABEL_ERRORS, data.get("error_count", 0))
                        show_bulk_errors(data)
                    else:
                        st.error(f"{resp.status_code}: {resp.json()}")
                except requests.exceptions.ConnectionError:
                    st.error(MSG_NO_CONNECTION)

    with tab_templates:
        st.subheader("Download CSV Templates")

        create_tpl = pd.DataFrame(columns=[
            "name", "price", "quantity", "description",
            "barcode", "category", "brand", "minimum_stock_level",
        ])
        st.download_button(
            "Bulk Create template",
            create_tpl.to_csv(index=False).encode(),
            "bulk_create_template.csv",
            MIME_CSV,
        )

        update_tpl = pd.DataFrame(columns=[
            "id", "name", "price", "quantity", "description",
            "barcode", "category", "brand", "minimum_stock_level",
        ])
        st.download_button(
            "Bulk Update template",
            update_tpl.to_csv(index=False).encode(),
            "bulk_update_template.csv",
            MIME_CSV,
        )

        delete_tpl = pd.DataFrame(columns=["id"])
        st.download_button(
            "Bulk Delete template",
            delete_tpl.to_csv(index=False).encode(),
            "bulk_delete_template.csv",
            MIME_CSV,
        )


elif section == NAV_SCENARIOS:
    st.title("Scenario Selector")
    st.markdown(
        "Select a scenario to populate the database with AI-generated products."
    )
    st.divider()
    SCENARIOS = {
        "Holiday Rush": {"icon": "🎄"},
        "Flash Sale": {"icon": "🔥"},
        "Back to School": {"icon": "🎒"},
        "Premium Electronics": {"icon": "💎"},
        "Warehouse Overstock": {"icon": "📦"},
    }

    col1, col2 = st.columns([2, 1])
    with col1:
        selected_scenario = st.selectbox(
            "Choose a Scenario",
            options=list(SCENARIOS.keys()),
            format_func=lambda x: f"{SCENARIOS[x]['icon']} {x}"
        )

    st.info(f"Selected: **{selected_scenario}** - Products will be AI-generated and added to database")

    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("✅ Populate DB with Scenario", use_container_width=True, type="primary"):
            st.info("⏳ Generating and populating products...")
            
            try:
                payload = {"scenario": selected_scenario}
                
                resp = requests.post(
                    f"{BASE_URL}/ai/scenarios/",
                    json=payload,
                    timeout=30
                )
                
                if resp.status_code == 201:
                    data = resp.json()
                    st.success("Successfully populated database!")
                    
                    col_a, col_b = st.columns(2)
                    col_a.metric("Products Created", len(data.get("products", [])))
                    col_b.metric("Scenario", data.get("scenario", selected_scenario))
                    
                    st.subheader("Created Products")
                    products_df = pd.DataFrame(data.get("products", []))
                    if not products_df.empty:
                        available_cols = [col for col in DISPLAY_COLUMNS if col in products_df.columns]
                        st.dataframe(
                            products_df[available_cols],
                            use_container_width=True,
                            hide_index=True
                        )
                    
                    fetch_all_products.clear()
                else:
                    st.error(f"Error {resp.status_code}: {resp.json()}")
            except requests.exceptions.ConnectionError:
                st.error(MSG_NO_CONNECTION)
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")
    
    with col_btn2:
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_all_products.clear()
            st.rerun()
