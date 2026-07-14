"""
XIOPATH Phantom Infrastructure — Identity Forge
=================================================
Generates complete synthetic identities for phantom account creation.
All identity data is randomized — no real member data is used except
locale/timezone matching from the member's device.

Educational purpose only.
"""

import secrets
import random
import string
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional


# ════════════════════════════════════════════════
# Name Databases (curated for believability)
# ════════════════════════════════════════════════

FIRST_NAMES = {
    "male": {
        "en": ["James", "Robert", "Michael", "David", "Richard", "Joseph", "Thomas", "Christopher",
               "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Paul", "Andrew", "Joshua",
               "Kenneth", "Kevin", "Brian", "George", "Timothy", "Ronald", "Edward", "Jason",
               "Jeffrey", "Ryan", "Jacob", "Gary", "Nicholas", "Eric", "Jonathan", "Stephen",
               "Larry", "Justin", "Scott", "Brandon", "Benjamin", "Samuel", "Raymond", "Gregory"],
        "hi": ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
               "Krishna", "Ishaan", "Shaurya", "Atharv", "Dhruv", "Kabir", "Ritvik", "Aarush",
               "Kian", "Darsh", "Yash", "Rishi", "Arnav", "Advait", "Pranav", "Rohan",
               "Vikram", "Nikhil", "Rahul", "Amit", "Suresh", "Rajesh"],
        "bn": ["Aritra", "Aniket", "Arjun", "Debojit", "Dipankar", "Gaurav", "Indranil",
               "Jayanta", "Kaushik", "Mainak", "Niloy", "Partha", "Rajdeep", "Sayan",
               "Sourav", "Subhajit", "Tanmoy", "Uday", "Vikash", "Writam"],
    },
    "female": {
        "en": ["Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
               "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
               "Ashley", "Dorothy", "Kimberly", "Emily", "Donna", "Michelle", "Carol",
               "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura",
               "Cynthia", "Kathleen", "Amy", "Angela", "Shirley", "Anna", "Brenda"],
        "hi": ["Aadhya", "Ananya", "Diya", "Isha", "Kiara", "Myra", "Prisha", "Riya",
               "Sara", "Saanvi", "Aanya", "Avni", "Bhavya", "Charvi", "Drishti", "Eesha",
               "Gauri", "Hiya", "Ira", "Jiya", "Kavya", "Lavanya", "Mahi", "Navya",
               "Ojasvi", "Pari", "Ridhi", "Sia", "Tara", "Urvi"],
        "bn": ["Aditi", "Ankita", "Anushka", "Devika", "Gargi", "Ishita", "Jaya",
               "Keya", "Madhurima", "Nandini", "Payel", "Priyanka", "Rima", "Sayani",
               "Shreya", "Sohini", "Swagata", "Tanisha", "Trisha", "Udita"],
    }
}

LAST_NAMES = {
    "en": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
           "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
           "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
           "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
           "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
           "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera"],
    "hi": ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Agarwal", "Joshi",
           "Mishra", "Rao", "Reddy", "Nair", "Iyer", "Pillai", "Menon", "Chauhan",
           "Thakur", "Malhotra", "Kapoor", "Bhatia", "Chopra", "Mehta", "Dutta", "Sen"],
    "bn": ["Banerjee", "Chatterjee", "Mukherjee", "Ghosh", "Bose", "Das", "Roy",
           "Sen", "Dutta", "Sarkar", "Chakraborty", "Bhattacharya", "Mitra", "Saha",
           "Pal", "Mondal", "Ganguly", "Majumdar", "Biswas", "Nag"],
}

LOCALE_MAP = {
    "en-US": {"lang": "en", "tz": "America/New_York"},
    "en-GB": {"lang": "en", "tz": "Europe/London"},
    "en-AU": {"lang": "en", "tz": "Australia/Sydney"},
    "hi-IN": {"lang": "hi", "tz": "Asia/Kolkata"},
    "bn-IN": {"lang": "bn", "tz": "Asia/Kolkata"},
    "en-IN": {"lang": "en", "tz": "Asia/Kolkata"},
}


class IdentityForge:
    """
    Generates complete synthetic identities for phantom account creation.
    Each identity is fully randomized with internally consistent demographics.
    """

    def __init__(self, locale: str = "en-US"):
        """
        Initialize the forge with a target locale.
        
        Args:
            locale: BCP-47 locale string (e.g., 'en-US', 'hi-IN', 'bn-IN').
                    Determines name database, timezone, and language preferences.
        """
        self.locale = locale
        locale_info = LOCALE_MAP.get(locale, LOCALE_MAP["en-US"])
        self.lang = locale_info["lang"]
        self.timezone = locale_info["tz"]

    def forge_identity(self, gender: Optional[str] = None) -> dict:
        """
        Generate a complete synthetic identity.
        
        Args:
            gender: 'male', 'female', or None (random)
        
        Returns:
            dict with all identity fields needed for account creation
        """
        if gender is None:
            gender = random.choice(["male", "female"])

        first_name = self._random_first_name(gender)
        last_name = self._random_last_name()
        dob = self._random_dob(min_age=18, max_age=55)
        username = self._generate_username(first_name, last_name)
        email = f"{username}@gmail.com"
        password = self._generate_strong_password()

        return {
            "first_name": first_name,
            "last_name": last_name,
            "dob": dob,
            "gender": gender,
            "email": email,
            "username": username,
            "password": password,
            "locale": self.locale,
            "timezone": self.timezone,
            "profile_picture_url": None,
        }

    def forge_batch(self, count: int, gender_distribution: Optional[dict] = None) -> list[dict]:
        """
        Generate multiple synthetic identities.
        
        Args:
            count: Number of identities to generate
            gender_distribution: Optional dict like {'male': 0.5, 'female': 0.5}
        
        Returns:
            List of identity dicts
        """
        identities = []
        for _ in range(count):
            if gender_distribution:
                gender = random.choices(
                    list(gender_distribution.keys()),
                    weights=list(gender_distribution.values())
                )[0]
            else:
                gender = None
            identities.append(self.forge_identity(gender))

        # Ensure all usernames/emails are unique
        seen_usernames = set()
        for identity in identities:
            while identity["username"] in seen_usernames:
                identity["username"] = self._generate_username(
                    identity["first_name"], identity["last_name"]
                )
                identity["email"] = f"{identity['username']}@gmail.com"
            seen_usernames.add(identity["username"])

        return identities

    def _random_first_name(self, gender: str) -> str:
        """Pick a random first name appropriate for the gender and locale."""
        gender_names = FIRST_NAMES.get(gender, FIRST_NAMES["male"])
        names = gender_names.get(self.lang, gender_names["en"])
        return random.choice(names)

    def _random_last_name(self) -> str:
        """Pick a random last name appropriate for the locale."""
        names = LAST_NAMES.get(self.lang, LAST_NAMES["en"])
        return random.choice(names)

    def _random_dob(self, min_age: int = 18, max_age: int = 55) -> str:
        """
        Generate a random date of birth as YYYY-MM-DD string.
        Age will be between min_age and max_age years.
        """
        today = datetime.now(timezone.utc).date()
        min_date = today - timedelta(days=max_age * 365)
        max_date = today - timedelta(days=min_age * 365)
        delta = (max_date - min_date).days
        random_date = min_date + timedelta(days=random.randint(0, delta))
        return random_date.strftime("%Y-%m-%d")

    def _generate_username(self, first_name: str, last_name: str) -> str:
        """
        Generate a believable Gmail username from name components.
        Uses multiple patterns to avoid predictability.
        """
        first = first_name.lower().replace(" ", "")
        last = last_name.lower().replace(" ", "")
        digits = str(random.randint(1, 9999))

        patterns = [
            f"{first}{last}{digits}",
            f"{first}.{last}{digits}",
            f"{first}{last[0]}{digits}",
            f"{first[0]}{last}{digits}",
            f"{first}.{last[0:3]}{digits}",
            f"{last}.{first}{digits}",
            f"{first}{digits}{last[0:2]}",
            f"{first}_{last}{random.randint(10, 99)}",
        ]
        return random.choice(patterns)

    def _generate_strong_password(self, length: int = 24) -> str:
        """
        Generate a cryptographically strong password.
        Guaranteed to contain uppercase, lowercase, digits, and symbols.
        """
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
        while True:
            password = ''.join(secrets.choice(alphabet) for _ in range(length))
            # Ensure all character types are represented
            has_upper = any(c.isupper() for c in password)
            has_lower = any(c.islower() for c in password)
            has_digit = any(c.isdigit() for c in password)
            has_symbol = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password)
            if has_upper and has_lower and has_digit and has_symbol:
                return password

    def match_locale_from_device(self, device_locale: str, device_timezone: str) -> "IdentityForge":
        """
        Create a new IdentityForge instance matched to the member's device locale.
        This ensures the phantom identity's demographics match the verification device.
        
        Args:
            device_locale: The member's device locale (e.g., 'en-US')
            device_timezone: The member's device timezone (e.g., 'America/New_York')
        
        Returns:
            New IdentityForge instance with matching locale
        """
        # Find the closest matching locale
        if device_locale in LOCALE_MAP:
            forge = IdentityForge(device_locale)
        else:
            # Fallback: match by language prefix
            lang_prefix = device_locale.split("-")[0]
            matched = None
            for loc_key, loc_info in LOCALE_MAP.items():
                if loc_key.startswith(lang_prefix):
                    matched = loc_key
                    break
            forge = IdentityForge(matched or "en-US")

        # Override timezone if different
        forge.timezone = device_timezone
        return forge


class IdentityValidator:
    """
    Validates a synthetic identity for internal consistency and believability.
    Catches issues before they reach a service's signup form.
    """

    @staticmethod
    def validate(identity: dict) -> tuple[bool, list[str]]:
        """
        Validate a synthetic identity dict.
        
        Returns:
            (is_valid, list_of_issues)
        """
        issues = []

        # Check required fields
        required = ["first_name", "last_name", "dob", "gender", "email",
                     "username", "password", "locale", "timezone"]
        for field in required:
            if not identity.get(field):
                issues.append(f"Missing required field: {field}")

        # Validate DOB
        if identity.get("dob"):
            try:
                dob = datetime.strptime(identity["dob"], "%Y-%m-%d").date()
                today = datetime.now(timezone.utc).date()
                age = (today - dob).days / 365
                if age < 13:
                    issues.append(f"Too young: age {age:.0f} (minimum 13)")
                if age > 100:
                    issues.append(f"Unrealistic age: {age:.0f}")
            except ValueError:
                issues.append(f"Invalid DOB format: {identity['dob']}")

        # Validate email format
        if identity.get("email"):
            email = identity["email"]
            if "@" not in email:
                issues.append(f"Invalid email: {email}")
            local_part = email.split("@")[0]
            if len(local_part) < 3:
                issues.append(f"Username too short: {local_part}")
            if len(local_part) > 30:
                issues.append(f"Username too long: {local_part}")

        # Validate password strength
        if identity.get("password"):
            pw = identity["password"]
            if len(pw) < 16:
                issues.append(f"Password too short: {len(pw)} chars (minimum 16)")

        # Validate gender
        if identity.get("gender") not in ("male", "female", "unspecified"):
            issues.append(f"Invalid gender: {identity.get('gender')}")

        return (len(issues) == 0, issues)


def generate_profile_picture_seed(identity: dict) -> str:
    """
    Generate a deterministic seed for AI profile picture generation.
    The same identity always produces the same seed (for consistency).
    
    Args:
        identity: The synthetic identity dict
    
    Returns:
        A hex string seed for image generation
    """
    seed_input = f"{identity['first_name']}:{identity['last_name']}:{identity['dob']}:{identity['gender']}"
    return hashlib.sha256(seed_input.encode()).hexdigest()[:16]
