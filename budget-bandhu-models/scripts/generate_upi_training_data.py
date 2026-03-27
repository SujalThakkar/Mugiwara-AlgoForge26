import pandas as pd
import random
import os

random.seed(42)

CATEGORIES = {
    "Food & Dining": [
        "ZOMATO*ORDER{}", "Swiggy Food Delivery", "McDonald's India",
        "Domino's Pizza Order", "Dunzo Quick Commerce", "Blinkit Instant",
        "Burger King India", "KFC India Order", "Pizza Hut Delivery",
        "Starbucks India", "Cafe Coffee Day", "Subway India",
        "zomato order khaana", "swiggy se khana", "food delivery online",
        "ZMT*ORD{}", "SWGY*{}", "restaurant bill payment",
        "Fassos Wrap", "Box8 Meals", "Faasos Online", "EatFit Health",
        "Behrouz Biryani", "Biryani By Kilo", "Haldirams Sweets",
        "khaana order", "lunch delivery", "dinner online order",
        "FOOD*DELIV*{}", "canteen payment", "mess fee online",
    ],
    "Transport": [
        "OLA*CAB*{}", "Uber India Trip", "IRCTC E-TICKET*{}",
        "RedBus Ticket Booking", "Rapido Bike Taxi", "Delhi Metro DMRC",
        "Mumbai Metro MMR", "BEST Bus Mumbai", "BMTC Bengaluru",
        "Ola Electric Scooter", "Yulu Bike Rental", "Vogo Scooter",
        "InDrive Cab", "Meru Cabs", "BluSmart EV Cab",
        "petrol pump payment", "fuel station HPCL", "BPCL Petrol",
        "Indian Oil Fuel", "auto rickshaw UPI", "cab booking fare",
        "UBER*TRIP*{}", "OLA*RIDE*{}", "train ticket booking",
        "bus ticket online", "metro card recharge", "parking fee",
    ],
    "Shopping": [
        "Amazon Pay India*{}", "Flipkart Internet Pvt", "Myntra Fashion",
        "Meesho App Purchase", "Nykaa Beauty Order", "Ajio Fashion",
        "Snapdeal Purchase", "ShopClues Order", "Tata CLiQ",
        "Reliance Digital", "Croma Electronics", "Vijay Sales",
        "H&M India Online", "Zara India", "Lifestyle Stores",
        "shopping online amazon", "flipkart order delivery",
        "AMZN*PAY*{}", "FLPKRT*{}", "clothes shopping",
        "electronics purchase", "mobile accessories", "gadget buy",
        "Decathlon Sports", "Nike India", "Adidas India Store",
        "Puma Online India", "Boat Audio Products", "boAt Lifestyle",
    ],
    "Entertainment": [
        "Netflix India Subscription", "Spotify Premium India",
        "BookMyShow Ticket*{}", "Disney+ Hotstar Premium",
        "YouTube Premium Monthly", "PVR Cinemas*{}", "INOX Movies",
        "Amazon Prime Video", "SonyLIV Premium", "ZEE5 Premium",
        "Gaana Music Pro", "JioSaavn Pro", "Apple Music India",
        "entertainment subscription", "ott platform payment",
        "NETFLIX*{}", "SPOTIFY*{}", "movie ticket booking",
        "concert ticket", "gaming purchase Steam", "PlayStation Store",
        "Xbox Game Pass", "Ludo King Premium", "MPL Gaming",
        "Dream11 contest", "fantasy sports entry", "WinZO Games",
    ],
    "Utilities & Bills": [
        "Jio Recharge RJIL*{}", "Airtel Prepaid Recharge",
        "BESCOM Electricity Bill", "Tata Power Mumbai Bill",
        "Mahanagar Gas Bill", "BWSSB Water Bill",
        "MSEDCL Electricity", "TNEB Power Bill", "CESC Kolkata",
        "Vodafone Idea Vi", "BSNL Landline", "Hathway Internet",
        "ACT Fibernet Bill", "Excitel Broadband", "Tikona Internet",
        "mobile recharge online", "electricity bill payment",
        "gas cylinder booking", "broadband bill pay",
        "JIO*RCHG*{}", "AIRTEL*{}", "utility bill",
        "DTH recharge Tata Sky", "Dish TV Recharge", "d2h recharge",
    ],
    "Healthcare": [
        "Apollo Pharmacy Order", "1mg Medicines Online",
        "Practo Consult Fee", "Netmeds Medicine Order",
        "Medplus Pharmacy", "PharmEasy Order",
        "doctor consultation fee", "hospital bill payment",
        "Max Hospital", "Fortis Healthcare", "Apollo Hospitals",
        "Manipal Hospital", "Narayana Health", "Columbia Asia",
        "lab test booking", "diagnostic center fee",
        "APOLLO*{}", "1MG*{}", "medicine purchase",
        "health checkup fee", "dental clinic payment",
        "eye clinic glasses", "gym membership fee", "yoga class",
        "Cult.fit Membership", "HealthifyMe Premium",
    ],
    "Education": [
        "Unacademy Learn Subscription", "Coursera India Course",
        "BYJU'S App Payment", "Udemy Course Purchase",
        "College Fee Payment*{}", "Library Fine Payment",
        "Vedantu Live Classes", "upGrad Course Fee",
        "Great Learning Program", "Simplilearn Course",
        "exam registration fee", "NEET coaching fee",
        "JEE preparation course", "tuition fee payment",
        "UNACAD*{}", "BYJU*{}", "online course payment",
        "book purchase Amazon", "educational material",
        "certification exam fee", "language learning app",
        "Duolingo Premium", "skill development course",
    ],
    "Travel": [
        "MakeMyTrip Hotel*{}", "Goibibo Flight Booking",
        "OYO Rooms Booking*{}", "Yatra.com Ticket",
        "Airbnb India Stay", "IRCTC Tatkal Ticket",
        "IndiGo Airlines", "Air India Ticket", "SpiceJet Booking",
        "Vistara Flight", "GoFirst Air", "AkasaAir Booking",
        "hotel booking online", "flight ticket purchase",
        "MMYT*{}", "GOIBO*{}", "travel booking",
        "resort booking", "holiday package", "tour payment",
        "TripAdvisor Hotel", "Treebo Hotels", "FabHotels",
        "holiday inn payment", "travel insurance", "visa fee",
    ],
    "Groceries": [
        "BigBasket BB Order*{}", "DMart Ready Grocery",
        "JioMart Kiryana Store", "Spencer's Retail",
        "Nature's Basket Order", "Zepto Quick Grocery",
        "Blinkit Grocery*{}", "Swiggy Instamart",
        "More Supermarket", "Reliance Fresh",
        "grocery shopping online", "sabzi mandi payment",
        "kirana store upi", "supermarket bill",
        "BIGBSKT*{}", "DMART*{}", "weekly grocery",
        "vegetables fruits purchase", "milk subscription daily",
        "Country Delight Milk", "Milkbasket Order",
        "fresh produce market", "organic grocery store",
    ],
    "Transfers & ATM": [
        "UPI/PhonePe/{}", "NEFT Transfer HDFC*{}",
        "SBI ATM Withdrawal", "Paytm Wallet Load",
        "Google Pay Send Money", "IMPS Transfer*{}",
        "bank transfer online", "money sent UPI",
        "ATM cash withdrawal", "RTGS Transfer",
        "GPay/Send/{}", "phonepe send", "paytm transfer",
        "UPI transfer friend", "split bill payment",
        "rent payment UPI", "landlord rent transfer",
        "friend money sent", "family transfer",
        "NEFT*{}", "IMPS*{}", "cash withdrawal ATM",
    ],
}

AMOUNTS = {
    "Food & Dining":      (80, 1200),
    "Transport":          (50, 800),
    "Shopping":           (199, 5000),
    "Entertainment":      (99, 999),
    "Utilities & Bills":  (99, 2500),
    "Healthcare":         (150, 3000),
    "Education":          (299, 8000),
    "Travel":             (500, 12000),
    "Groceries":          (200, 2500),
    "Transfers & ATM":    (500, 15000),
}


def generate_description(template: str) -> str:
    if "{}" in template:
        return template.format(random.randint(10000, 99999))
    return template


def generate_samples(n_per_category: int = 350) -> pd.DataFrame:
    rows = []
    for category, templates in CATEGORIES.items():
        lo, hi = AMOUNTS[category]
        for _ in range(n_per_category):
            tmpl = random.choice(templates)
            desc = generate_description(tmpl)
            amount = round(random.uniform(lo, hi), 2)
            rows.append({"description": desc, "category": category, "amount": amount})
    df = pd.DataFrame(rows).sample(frac=1, random_state=42).reset_index(drop=True)
    return df


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    df = generate_samples(350)
    out = "data/upi_training_data.csv"
    df.to_csv(out, index=False)
    print(f"Generated {len(df)} training samples → {out}")
    print(df["category"].value_counts())