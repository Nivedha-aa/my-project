import os
import re
import json
import urllib.parse
from PIL import Image
from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

if not API_KEY or API_KEY == "your_gemini_api_key_here":
    # Fallback to mock mode if key isn't populated
    client = None
else:
    client = genai.Client(api_key=API_KEY)


def extract_json_from_response(text: str) -> dict:
    """Extracts and parses JSON from standard text or markdown block code."""
    try:
        return json.loads(text)
    except Exception:
        pass

    # Clean markdown block markers
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        clean_text = match.group(1).strip()
        try:
            return json.loads(clean_text)
        except Exception:
            pass

    # Regex search for basic JSON dict pattern
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    raise ValueError("Could not parse valid JSON from AI response.")


def get_home_recommendations(budget_input: dict) -> dict:
    total_budget = float(budget_input.get("total_budget", 0))
    num_lights = int(budget_input.get("num_lights", 0))
    num_fans = int(budget_input.get("num_fans", 0))
    num_furniture = int(budget_input.get("num_furniture", 0))
    num_dining = int(budget_input.get("num_dining_tables", 0))

    rooms = []
    if budget_input.get("has_living_room"):
        rooms.append("Living Room")
    if budget_input.get("has_kitchen"):
        rooms.append("Kitchen")
    if budget_input.get("has_bedroom"):
        rooms.append("Bedroom")

    rooms_str = ", ".join(rooms) if rooms else "General Spaces"
    add_reqs = budget_input.get("additional_requirements") or "None"

    prompt = f"""
    I need interior design product recommendations for a home in India with a total budget of ₹{total_budget:.2f}.
    Requirements:
    - {num_lights} lights/lighting fixtures
    - {num_fans} ceiling fans
    - {num_furniture} furniture pieces
    - {num_dining} dining tables
    
    Target Rooms: {rooms_str}
    Additional requirements: {add_reqs}

    Please provide a detailed budget breakdown with product recommendations available in India.
    Use Indian brands and pricing in INR. Include search terms suitable for Indian shopping platforms.

    Format your response STRICTLY as a valid JSON object matching this structure:
    {{
      "total_budget": {total_budget},
      "remaining_budget": 0.0,
      "budget_breakdown": [
        {{
          "category": "Lighting",
          "allocation": 0.0,
          "items": [
            {{
              "name": "Sample Light",
              "description": "LED Light",
              "estimated_price": 0.0,
              "quantity": 1,
              "search_terms": "LED warm ceiling light"
            }}
          ]
        }}
      ],
      "calculation_table": [
        {{
          "category": "Lighting",
          "items_count": 1,
          "total_cost": 0.0,
          "percentage_of_budget": 0.0
        }}
      ],
      "additional_suggestions": ["Tip 1", "Tip 2"]
    }}
    Ensure all total costs stay within budget.
    """

    if not client:
        return generate_mock_home_response(total_budget)

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash", contents=prompt
        )
        result = extract_json_from_response(response.text)
    except Exception as e:
        print(f"Gemini API Error/Fallback: {e}")
        return generate_mock_home_response(total_budget)

    # Attach generated e-commerce search links
    for category in result.get("budget_breakdown", []):
        for item in category.get("items", []):
            st = item.get("search_terms", "")
            if st:
                encoded = urllib.parse.quote_plus(st)
                item["shopping_links"] = {
                    "amazon": f"https://www.amazon.in/s?k={encoded}",
                    "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                    "ikea": f"https://www.ikea.com/in/en/search/?q={encoded}",
                    "myntra": f"https://www.myntra.com/search?q={encoded}",
                    "ajio": f"https://www.ajio.com/search/?text={encoded}",
                }

    return result


def get_party_recommendations(budget_input: dict) -> dict:
    total_budget = float(budget_input.get("total_budget", 0))
    party_type = budget_input.get("party_type", "General Party")
    num_guests = int(budget_input.get("num_guests", 10))
    venue_type = budget_input.get("venue_type") or "Not specified"
    needs_catering = "Yes" if budget_input.get("needs_catering") else "No"
    needs_decor = "Yes" if budget_input.get("needs_decoration") else "No"
    needs_ent = "Yes" if budget_input.get("needs_entertainment") else "No"
    add_reqs = budget_input.get("additional_requirements") or "None"

    prompt = f"""
    I need party planning recommendations for India with a total budget of ₹{total_budget:.2f}.
    Party Details:
    - Type: {party_type}
    - Guest Count: {num_guests}
    - Venue Type: {venue_type}
    - Catering Needed: {needs_catering}
    - Decoration Needed: {needs_decor}
    - Entertainment Needed: {needs_ent}
    - Additional Requirements: {add_reqs}

    Provide recommendations with specific items, services, and venue suggestions in INR.
    Format your response STRICTLY as a JSON object with this schema:
    {{
      "total_budget": {total_budget},
      "remaining_budget": 0.0,
      "budget_breakdown": [
        {{
          "category": "catering",
          "allocation": 0.0,
          "items": [
            {{
              "name": "Buffet Catering",
              "description": "Standard Veg Buffet",
              "estimated_price": 0.0,
              "quantity": 1,
              "search_terms": "party catering services"
            }}
          ]
        }}
      ],
      "venue_suggestions": [
        {{
          "name": "Sample Banquet Hall",
          "type": "Indoor",
          "capacity": {num_guests},
          "estimated_cost": 0.0,
          "search_terms": "banquet halls in chennai"
        }}
      ],
      "additional_suggestions": ["Suggestion 1"]
    }}
    Ensure all costs are in INR and total does not exceed the given budget.
    """

    if not client:
        return generate_mock_party_response(total_budget)

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash", contents=prompt
        )
        result = extract_json_from_response(response.text)
    except Exception as e:
        print(f"Gemini API Error/Fallback: {e}")
        return generate_mock_party_response(total_budget)

    # Attach multi-platform links based on party categories
    cat_platforms = {
        "venue": ["google", "booking", "makemytrip", "oyorooms", "nobroker"],
        "catering": ["swiggy", "zomato"],
        "food": ["swiggy", "zomato", "bigbasket", "amazon"],
        "decoration": ["amazon", "flipkart", "meesho"],
        "entertainment": ["bookmyshow", "amazon", "flipkart"],
    }
    default_platforms = ["amazon", "flipkart", "google"]

    for category in result.get("budget_breakdown", []):
        cat_name = category.get("category", "").lower()
        platforms = cat_platforms.get(cat_name, default_platforms)
        for item in category.get("items", []):
            st = item.get("search_terms", "")
            if st:
                encoded = urllib.parse.quote_plus(st)
                links = {}
                if "amazon" in platforms:
                    links["amazon"] = f"https://www.amazon.in/s?k={encoded}"
                if "flipkart" in platforms:
                    links[
                        "flipkart"
                    ] = f"https://www.flipkart.com/search?q={encoded}"
                if "swiggy" in platforms:
                    links[
                        "swiggy"
                    ] = f"https://www.swiggy.com/search?query={encoded}"
                if "zomato" in platforms:
                    links["zomato"] = f"https://www.zomato.com/search?q={encoded}"
                if "bookmyshow" in platforms:
                    links[
                        "bookmyshow"
                    ] = f"https://in.bookmyshow.com/search?q={encoded}"
                if "google" in platforms:
                    links["google"] = f"https://www.google.com/search?q={encoded}"
                item["shopping_links"] = links

    for venue in result.get("venue_suggestions", []):
        st = venue.get("search_terms", "")
        if st:
            encoded = urllib.parse.quote_plus(st)
            venue["search_links"] = {
                "google": f"https://www.google.com/search?q={encoded}",
                "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={encoded}",
                "oyorooms": f"https://www.oyorooms.com/search/?location={encoded}",
            }

    return result


def get_jewelry_recommendations(
    budget_input: dict, image_path: str = None
) -> dict:
    total_budget = float(budget_input.get("total_budget", 0))
    occasion = budget_input.get("occasion", "General")
    preferences = budget_input.get("preferences") or "Not specified"

    base_prompt = f"""
    I need jewelry recommendations for India with a total budget of ₹{total_budget:.2f}.
    Occasion: {occasion}
    Preferences: {preferences}
    Provide only India-relevant styles, availability, and price ranges in INR.
    """

    if image_path and os.path.exists(image_path):
        prompt = (
            base_prompt
            + """
        An image of the outfit is uploaded. Analyze the image and suggest jewelry that complements it (considering color, style, and formality).
        Format your response STRICTLY as a JSON object:
        {
          "outfit_analysis": {
            "colors": ["White", "Silver"],
            "style": "Casual Elegant",
            "formality": "Semi-formal"
          },
          "total_budget": """
            + str(total_budget)
            + """,
          "remaining_budget": 0.0,
          "jewelry_recommendations": [
            {
              "item_type": "Bracelet",
              "description": "Silver braided chain",
              "style": "Minimalist",
              "estimated_price": 0.0,
              "search_terms": "silver braided bracelet women"
            }
          ],
          "styling_tips": ["Tip 1", "Tip 2"]
        }
        """
        )
    else:
        prompt = (
            base_prompt
            + """
        Format your response STRICTLY as a JSON object:
        {
          "outfit_analysis": {
            "colors": ["N/A"],
            "style": "N/A",
            "formality": "N/A"
          },
          "total_budget": """
            + str(total_budget)
            + """,
          "remaining_budget": 0.0,
          "jewelry_recommendations": [
            {
              "item_type": "Necklace",
              "description": "Gold plated pendant necklace",
              "style": "Traditional",
              "estimated_price": 0.0,
              "search_terms": "gold plated pendant necklace"
            }
          ],
          "styling_tips": ["Tip 1", "Tip 2"]
        }
        """
        )

    if not client:
        return generate_mock_jewelry_response(
            total_budget, has_image=bool(image_path)
        )

    try:
        if image_path and os.path.exists(image_path):
            img = Image.open(image_path)
            response = client.models.generate_content(
                model="gemini-1.5-flash", contents=[prompt, img]
            )
        else:
            response = client.models.generate_content(
                model="gemini-1.5-flash", contents=prompt
            )

        result = extract_json_from_response(response.text)
    except Exception as e:
        print(f"Gemini API Error/Fallback: {e}")
        return generate_mock_jewelry_response(
            total_budget, has_image=bool(image_path)
        )

    for item in result.get("jewelry_recommendations", []):
        st = item.get("search_terms", "")
        if st:
            encoded = urllib.parse.quote_plus(st)
            item["shopping_links"] = {
                "amazon": f"https://www.amazon.in/s?k={encoded}",
                "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                "bluestone": f"https://www.bluestone.com/search.html?query={encoded}",
                "tanishq": f"https://www.tanishq.co.in/search?q={encoded}",
                "caratlane": f"https://www.caratlane.com/search?q={encoded}",
            }

    return result


# Fallback/Mock Response Generators
def generate_mock_home_response(budget: float) -> dict:
    alloc = budget * 0.9
    rem = budget - alloc
    return {
        "total_budget": budget,
        "remaining_budget": rem,
        "budget_breakdown": [
            {
                "category": "Lighting",
                "allocation": budget * 0.3,
                "items": [
                    {
                        "name": "LED Warm Ceiling Bulb Pack",
                        "description": "Energy efficient LED warm light bulbs",
                        "estimated_price": budget * 0.1,
                        "quantity": 2,
                        "search_terms": "LED ceiling lights",
                        "shopping_links": {
                            "amazon": "https://www.amazon.in/s?k=LED+ceiling+lights",
                            "flipkart": "https://www.flipkart.com/search?q=LED+ceiling+lights",
                        },
                    }
                ],
            },
            {
                "category": "Ceiling Fans",
                "allocation": budget * 0.4,
                "items": [
                    {
                        "name": "Havells High Speed Ceiling Fan",
                        "description": "Aerodynamic fan with low energy consumption",
                        "estimated_price": budget * 0.35,
                        "quantity": 1,
                        "search_terms": "Havells ceiling fan",
                        "shopping_links": {
                            "amazon": "https://www.amazon.in/s?k=Havells+ceiling+fan",
                            "flipkart": "https://www.flipkart.com/search?q=Havells+ceiling+fan",
                        },
                    }
                ],
            },
        ],
        "calculation_table": [
            {
                "category": "Lighting",
                "items_count": 2,
                "total_cost": budget * 0.2,
                "percentage_of_budget": 20.0,
            },
            {
                "category": "Ceiling Fans",
                "items_count": 1,
                "total_cost": budget * 0.35,
                "percentage_of_budget": 35.0,
            },
        ],
        "additional_suggestions": [
            "Opt for modular furniture to optimize small spaces.",
            "Look for festive sales on e-commerce platforms to maximize savings.",
        ],
    }


def generate_mock_party_response(budget: float) -> dict:
    return {
        "total_budget": budget,
        "remaining_budget": budget * 0.1,
        "budget_breakdown": [
            {
                "category": "catering",
                "allocation": budget * 0.5,
                "items": [
                    {
                        "name": "Party Snack Box & Buffet",
                        "description": "Assorted vegetarian & non-vegetarian platter",
                        "estimated_price": budget * 0.45,
                        "quantity": 10,
                        "search_terms": "swiggy party catering",
                        "shopping_links": {
                            "swiggy": "https://www.swiggy.com",
                            "zomato": "https://www.zomato.com",
                        },
                    }
                ],
            },
            {
                "category": "decoration",
                "allocation": budget * 0.3,
                "items": [
                    {
                        "name": "Party Balloon & Banner Arch",
                        "description": "Complete DIY party decor set",
                        "estimated_price": budget * 0.25,
                        "quantity": 1,
                        "search_terms": "party decorations set",
                        "shopping_links": {
                            "amazon": "https://www.amazon.in/s?k=party+decorations+set"
                        },
                    }
                ],
            },
        ],
        "venue_suggestions": [
            {
                "name": "Green Meadows Celebration Hall",
                "type": "Banquet",
                "capacity": 25,
                "estimated_cost": budget * 0.2,
                "search_terms": "celebration hall venue",
                "search_links": {
                    "google": "https://www.google.com/search?q=celebration+hall+venue"
                },
            }
        ],
        "additional_suggestions": [
            "Consider potluck style desserts to reduce catering costs.",
            "Use ambient string lights for inexpensive venue decoration.",
        ],
    }


def generate_mock_jewelry_response(
    budget: float, has_image: bool = False
) -> dict:
    return {
        "outfit_analysis": {
            "colors": ["Cream", "Gold"] if has_image else ["N/A"],
            "style": "Traditional Elegant" if has_image else ["N/A"],
            "formality": "Festive / Wedding" if has_image else ["N/A"],
        },
        "total_budget": budget,
        "remaining_budget": budget * 0.15,
        "jewelry_recommendations": [
            {
                "item_type": "Earrings",
                "description": "Gold Plated Kundan Jhumka Earrings",
                "style": "Ethnic Traditional",
                "estimated_price": budget * 0.4,
                "search_terms": "gold plated kundan jhumka",
                "shopping_links": {
                    "amazon": "https://www.amazon.in/s?k=gold+kundan+jhumka",
                    "tanishq": "https://www.tanishq.co.in",
                },
            },
            {
                "item_type": "Necklace",
                "description": "Choker Necklace Set with Pearls",
                "style": "Royal Pearl",
                "estimated_price": budget * 0.45,
                "search_terms": "pearl choker necklace set",
                "shopping_links": {
                    "caratlane": "https://www.caratlane.com",
                    "flipkart": "https://www.flipkart.com",
                },
            },
        ],
        "styling_tips": [
            "Match warm metallic tones with golden-embroidered outfits.",
            "Keep necklines open when wearing statement choker necklaces.",
        ],
    }