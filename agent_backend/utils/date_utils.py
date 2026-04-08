import re
from datetime import datetime, timedelta
import calendar

class DateParser:
    """Utility class for parsing date-related information from text queries"""
    
    def __init__(self):
        # Month name mappings
        self.month_names = {
            "january": 1, "jan": 1,
            "february": 2, "feb": 2,
            "march": 3, "mar": 3,
            "april": 4, "apr": 4,
            "may": 5,
            "june": 6, "jun": 6,
            "july": 7, "jul": 7,
            "august": 8, "aug": 8,
            "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10,
            "november": 11, "nov": 11,
            "december": 12, "dec": 12
        }
        
        # Day name mappings
        self.day_names = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "thurs": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6
        }
        
        # Ordinal number mappings
        self.ordinal_numbers = {
            "first": 1, "1st": 1,
            "second": 2, "2nd": 2,
            "third": 3, "3rd": 3,
            "fourth": 4, "4th": 4,
            "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6,
            "seventh": 7, "7th": 7,
            "eighth": 8, "8th": 8,
            "ninth": 9, "9th": 9,
            "tenth": 10, "10th": 10,
            "eleventh": 11, "11th": 11,
            "twelfth": 12, "12th": 12,
            "thirteenth": 13, "13th": 13,
            "fourteenth": 14, "14th": 14,
            "fifteenth": 15, "15th": 15,
            "sixteenth": 16, "16th": 16,
            "seventeenth": 17, "17th": 17,
            "eighteenth": 18, "18th": 18,
            "nineteenth": 19, "19th": 19,
            "twentieth": 20, "20th": 20,
            "twenty-first": 21, "21st": 21,
            "twenty-second": 22, "22nd": 22,
            "twenty-third": 23, "23rd": 23,
            "twenty-fourth": 24, "24th": 24,
            "twenty-fifth": 25, "25th": 25,
            "twenty-sixth": 26, "26th": 26,
            "twenty-seventh": 27, "27th": 27,
            "twenty-eighth": 28, "28th": 28,
            "twenty-ninth": 29, "29th": 29,
            "thirtieth": 30, "30th": 30,
            "thirty-first": 31, "31st": 31
        }
        
        # Quarter mappings
        self.quarter_mappings = {
            "q1": (1, 3),  # (start_month, end_month)
            "first quarter": (1, 3),
            "1st quarter": (1, 3),
            "q2": (4, 6),
            "second quarter": (4, 6),
            "2nd quarter": (4, 6),
            "q3": (7, 9),
            "third quarter": (7, 9),
            "3rd quarter": (7, 9),
            "q4": (10, 12),
            "fourth quarter": (10, 12),
            "4th quarter": (10, 12)
        }
        
        # Relative time expressions
        self.relative_time = {
            "today": 0,
            "yesterday": -1,
            "tomorrow": 1,
            "last week": -7,
            "next week": 7,
            "last month": -30,
            "next month": 30
        }
    
    def extract_date_parts(self, query):
        """
        Extract date-related parts from a query
        Returns:
            - extracted_parts: dict with date components
            - clean_query: query with date parts removed
        """
        query = query.lower()
        original_query = query
        extracted_parts = {
            "year": None,
            "month": None,
            "month_name": None,
            "day": None,
            "weekday": None,
            "quarter": None,
            "relative_days": None
        }
        
        # Extract years (e.g., 2025, '25)
        year_patterns = [
            r'\b(20\d{2})\b',  # 2025
            r'\b\'(\d{2})\b'    # '25
        ]
        
        for pattern in year_patterns:
            year_match = re.search(pattern, query)
            if year_match:
                year_str = year_match.group(1)
                if len(year_str) == 2:
                    extracted_parts["year"] = 2000 + int(year_str)
                else:
                    extracted_parts["year"] = int(year_str)
                query = re.sub(pattern, ' ', query)
        
        # Extract month names
        month_pattern = r'\b(' + '|'.join(self.month_names.keys()) + r')\b'
        month_match = re.search(month_pattern, query)
        if month_match:
            month_name = month_match.group(1)
            extracted_parts["month"] = self.month_names[month_name]
            extracted_parts["month_name"] = calendar.month_name[self.month_names[month_name]].lower()
            query = re.sub(r'\b' + re.escape(month_name) + r'\b', ' ', query)
        
        # Extract day numbers (1-31)
        day_pattern = r'\b(\d{1,2})(?:st|nd|rd|th)?\b'
        day_match = re.search(day_pattern, query)
        if day_match:
            day = int(day_match.group(1))
            if 1 <= day <= 31:
                extracted_parts["day"] = day
                query = re.sub(day_pattern, ' ', query)
        
        # Extract ordinal day numbers (first, second, etc.)
        ordinal_pattern = r'\b(' + '|'.join(self.ordinal_numbers.keys()) + r')\b'
        ordinal_match = re.search(ordinal_pattern, query)
        if ordinal_match:
            ordinal = ordinal_match.group(1)
            extracted_parts["day"] = self.ordinal_numbers[ordinal]
            query = re.sub(r'\b' + re.escape(ordinal) + r'\b', ' ', query)
        
        # Extract weekday names
        weekday_pattern = r'\b(' + '|'.join(self.day_names.keys()) + r')\b'
        weekday_match = re.search(weekday_pattern, query)
        if weekday_match:
            weekday = weekday_match.group(1)
            extracted_parts["weekday"] = calendar.day_name[self.day_names[weekday]].lower()
            query = re.sub(r'\b' + re.escape(weekday) + r'\b', ' ', query)
        
        # Extract quarters
        quarter_pattern = r'\b(' + '|'.join(self.quarter_mappings.keys()) + r')\b'
        quarter_match = re.search(quarter_pattern, query)
        if quarter_match:
            quarter = quarter_match.group(1)
            extracted_parts["quarter"] = self.quarter_mappings[quarter]
            query = re.sub(r'\b' + re.escape(quarter) + r'\b', ' ', query)
        
        # Extract relative time expressions
        relative_pattern = r'\b(' + '|'.join(self.relative_time.keys()) + r')\b'
        relative_match = re.search(relative_pattern, query)
        if relative_match:
            relative_expr = relative_match.group(1)
            extracted_parts["relative_days"] = self.relative_time[relative_expr]
            query = re.sub(r'\b' + re.escape(relative_expr) + r'\b', ' ', query)
        
        # Clean up the query
        clean_query = re.sub(r'\s+', ' ', query).strip()
        
        # If nothing was extracted, return original query
        if all(v is None for v in extracted_parts.values()):
            return {}, original_query
            
        return extracted_parts, clean_query
    
    def build_date_query(self, date_parts):
        """
        Build a MongoDB query from extracted date parts
        """
        if not date_parts:
            return {}
            
        query_conditions = []
        
        # Handle year
        if date_parts.get("year"):
            query_conditions.append({"year": date_parts["year"]})
        
        # Handle month
        if date_parts.get("month"):
            query_conditions.append({"month": date_parts["month"]})
        
        # Handle day
        if date_parts.get("day"):
            query_conditions.append({"day": date_parts["day"]})
        
        # Handle weekday
        if date_parts.get("weekday"):
            query_conditions.append({"weekday": date_parts["weekday"]})
        
        # Handle quarter
        if date_parts.get("quarter"):
            start_month, end_month = date_parts["quarter"]
            query_conditions.append({"month": {"$gte": start_month, "$lte": end_month}})
        
        # Handle relative days
        if date_parts.get("relative_days") is not None:
            today = datetime.now()
            target_date = today + timedelta(days=date_parts["relative_days"])
            query_conditions.append({
                "year": target_date.year,
                "month": target_date.month,
                "day": target_date.day
            })
        
        # Combine conditions with $and
        if query_conditions:
            return {"$and": query_conditions}
        
        return {}

# Example usage
if __name__ == "__main__":
    parser = DateParser()
    
    # Test with a few examples
    test_queries = [
        "emails from June 7th 2025",
        "meetings on Monday",
        "budget for Q3",
        "security alerts from last week",
        "project deadline for 15th of July",
        "emails about leave in June"
    ]
    
    for query in test_queries:
        date_parts, clean_query = parser.extract_date_parts(query)
        mongo_query = parser.build_date_query(date_parts)
        print(f"Original: '{query}'")
        print(f"Clean: '{clean_query}'")
        print(f"Date parts: {date_parts}")
        print(f"MongoDB query: {mongo_query}")
        print("-" * 50) 