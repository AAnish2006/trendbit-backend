import asyncio
import os
import sys
sys.path.append(os.path.dirname(__file__))

from apple_verifier import verify_ios_app
import supabase_client

async def main():
    url = "https://apps.apple.com/us/app/cal-ai-calorie-tracker/id6480417616"
    print("Verifying Cal AI with Apple iTunes API...")
    data = await verify_ios_app(url)
    print(f"Verified: {data['name']} by {data['seller_name']} (Rating: {data['rating']}, Genre: {data['primary_genre']})")

    product_payload = {
        "app_id": str(data["track_id"]),
        "name": data["name"],
        "website": data["app_store_url"],
        "clean_domain": f"apps.apple.com • {data['primary_genre']}",
        "developer": data["seller_name"],
        "genre": data["primary_genre"],
        "rating": float(data["rating"]) if data.get("rating") else 4.8,
        "price": data.get("price", "Free"),
        "tagline": (data.get("description") or "AI Calorie Tracker")[:120],
        "description": data.get("description", ""),
        "logo_url": data["icon_url"],
        "screenshot_url": data.get("screenshot_url", ""),
        "bid_amount": 8.0,
        "clicks": 0,
        "payment_status": "completed"
    }

    print("Saving to Supabase...")
    saved = await supabase_client.create_or_update_product(product_payload)
    print("Successfully saved to Supabase:", saved)

if __name__ == "__main__":
    asyncio.run(main())
