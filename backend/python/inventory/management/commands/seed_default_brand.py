from django.core.management.base import BaseCommand
from django.conf import settings
from pymongo import MongoClient

DEFAULT_BRAND = "Other"

class Command(BaseCommand):
    def handle(self, *args, **options):
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        products_col = db["products"]
        cursor = products_col.find(
            {
                "is_deleted": {"$ne": True},
                "$or": [
                    {"brand": {"$exists": False}},
                    {"brand": None},
                    {"brand": ""},
                ],
            },
            {"_id": 1, "name": 1, "brand": 1},
        )
        updated = 0
        for doc in cursor:
            self.stdout.write(
                f"'Updating'"
                f"_id={doc['_id']}  name='{doc.get('name', '')}' "
                f"brand='{doc.get('brand', '')}' = '{DEFAULT_BRAND}'"
            )
            products_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"brand": DEFAULT_BRAND}},
            )
            updated += 1

        client.close()
        summary = (
            f"\nDone. {updated} product(s) updated with brand='{DEFAULT_BRAND}'."
        )
        self.stdout.write(self.style.SUCCESS(summary))
