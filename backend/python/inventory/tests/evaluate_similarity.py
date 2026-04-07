import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_app.settings')
import django
django.setup()

from inventory.tests.similarity import eval_set
from inventory.services.vector_service import VectorService
from inventory.adapters.qdrant_repository import vector_repository
from inventory.adapters.product_repository import product_repository
from inventory.adapters.e5_base_instruct import embedding_provider
from inventory.adapters.python_logger import PythonProductLogger

logger = PythonProductLogger()

# MRR => Mean Reciprocal Rank
# Precision@K => Proportion of relevant items in the top K results
# Recall@K => Proportion of relevant items retrieved in the top K results

def calculate_metrics(results, relevant, k):
    retrieved_names = [res.get('name', '') for res in results[:k]]
    true_positives = sum(1 for name in retrieved_names if name in relevant)
    precision = true_positives / k if k > 0 else 0
    recall = true_positives / len(relevant) if len(relevant) > 0 else 0
    rr = 0
    for i, name in enumerate(retrieved_names):
        if name in relevant:
            rr = 1 / (i + 1)
            break
            
    return precision, recall, rr

def evaluate():
    vector_service = VectorService(
        vector_repository=vector_repository,
        product_repository=product_repository,
        embedding_provider=embedding_provider,
        logger=logger
    )
    
    K = 5
    total_precision = 0
    total_recall = 0
    total_rr = 0
    num_queries = len(eval_set)
    
    print(f"Starting evaluation of {num_queries} queries (K={K})...\n")

    for idx, eval_item in enumerate(eval_set):
        query = eval_item['query']
        relevant = eval_item['relevant']

        print(f"[{idx+1}/{num_queries}] Query: '{query}'")
        product_id = None
        doc = product_repository._collection.find_one({'name': query, 'is_deleted': {'$ne': True}})
        if doc:
            product_id = str(doc['_id'])

        if product_id:
            print(f"  Found product equivalent to query, id: {product_id}")
            results = vector_service.top_k_similar_products(product_id=product_id, top_k=K)
        else:
            print(f"  Could not find product for query, falling back to text query")
            results = vector_service.top_k_similar_products(query=query, top_k=K)

        precision, recall, rr = calculate_metrics(results, relevant, K)
        total_precision += precision
        total_recall += recall
        total_rr += rr
        
        print(f"  Precision@{K}: {precision:.4f} | Recall@{K}: {recall:.4f} | RR: {rr:.4f}")
        print("  Retrieved:")
        for r in results[:K]:
            print(f"    - {r.get('name', 'Unknown')} (Score: {r.get('score', 'N/A')})")
        print()
        
    mrr = total_rr / num_queries
    avg_precision = total_precision / num_queries
    avg_recall = total_recall / num_queries
    
    print("="*40)
    print("FINAL EVALUATION METRICS")
    print("="*40)
    print(f"Queries evaluated : {num_queries}")
    print(f"Mean Reciprocal Rank (MRR): {mrr:.4f}")
    print(f"Average Precision@{K}     : {avg_precision:.4f}")
    print(f"Average Recall@{K}        : {avg_recall:.4f}")
    print("="*40)

if __name__ == "__main__":
    evaluate()
