import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, List, Optional, Tuple
import sys
from datetime import datetime

class CornellCourseScraper:
    """Scraper for Cornell University course information with extended semester fallback."""
    
    BASE_URL = "https://classes.cornell.edu/browse/roster/{}/class/{}/{}"
    
    def __init__(self, semester: str = None, debug: bool = False):
        """
        Initialize the scraper.
        
        Args:
            semester: Semester code (e.g., "FA25" for Fall 2025, "SP25" for Spring 2025)
                     If None, automatically determines current semester
            debug: If True, print debug information during scraping
        """
        self.debug = debug
        if semester:
            self.semester = semester
        else:
            self.semester = self.get_current_semester()
            if self.debug:
                print(f"Debug: Auto-detected semester: {self.semester}")
        
        self.session = requests.Session()
        # Add headers to appear more like a regular browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    @staticmethod
    def get_current_semester() -> str:
        """
        Determine the current semester based on today's date.
        
        Returns:
            Semester code (e.g., "FA25", "SP26")
        """
        today = datetime.now()
        year = today.year
        month = today.month
        day = today.day
        
        # April 15 - October 14: Fall semester of current year
        if (month == 4 and day >= 15) or (5 <= month <= 9) or (month == 10 and day <= 14):
            return f"FA{year % 100:02d}"
        
        # October 15 - December 31: Spring semester of next year
        elif (month == 10 and day >= 15) or (11 <= month <= 12):
            return f"SP{(year + 1) % 100:02d}"
        
        # January 1 - April 14: Spring semester of current year
        else:  # month <= 3 or (month == 4 and day < 15)
            return f"SP{year % 100:02d}"
    
    @staticmethod
    def get_previous_semester(semester: str, steps_back: int = 1) -> str:
        """
        Get a previous semester code by going back a specified number of semesters.
        
        Args:
            semester: Current semester code (e.g., "FA25")
            steps_back: Number of semesters to go back (default 1)
            
        Returns:
            Previous semester code (e.g., "SP25")
        """
        current = semester
        for _ in range(steps_back):
            if current.startswith("FA"):
                # Fall -> previous Spring (same year)
                year = current[2:]
                current = f"SP{year}"
            elif current.startswith("SP"):
                # Spring -> previous Fall (previous year)
                year = int(current[2:])
                prev_year = year - 1
                current = f"FA{prev_year:02d}"
            else:
                # Unknown format, return as-is
                return current
        return current
    
    @staticmethod
    def get_fallback_semesters(semester: str, num_fallbacks: int = 3) -> List[str]:
        """
        Get a list of fallback semesters to check.
        
        Args:
            semester: Starting semester code
            num_fallbacks: Number of previous semesters to include (default 3)
            
        Returns:
            List of semester codes to check as fallbacks
        """
        fallbacks = []
        for i in range(1, num_fallbacks + 1):
            fallbacks.append(CornellCourseScraper.get_previous_semester(semester, i))
        return fallbacks
    
    def parse_course_code(self, course_string: str) -> Tuple[str, str]:
        """
        Parse a course string like "CS 1110" into department and number.
        
        Args:
            course_string: Course string (e.g., "CS 1110")
            
        Returns:
            Tuple of (department, course_number)
        """
        # Handle various formats: "CS 1110", "CS1110", "CS 1110: Title"
        course_string = course_string.strip()
        # Remove everything after colon if present
        if ':' in course_string:
            course_string = course_string.split(':')[0].strip()
        
        # Try to match department and number
        match = re.match(r'([A-Z]+)\s*(\d+)', course_string, re.IGNORECASE)
        if match:
            return match.group(1).upper(), match.group(2)
        else:
            raise ValueError(f"Could not parse course code: {course_string}")
    
    def get_course_info_for_semester(self, course_code: str, semester: str) -> Optional[Dict[str, str]]:
        """
        Get information for a single course in a specific semester.
        
        Args:
            course_code: Course code (e.g., "CS 1110")
            semester: Semester code (e.g., "FA25")
            
        Returns:
            Dictionary with course information or None if error/not found
        """
        try:
            dept, number = self.parse_course_code(course_code)
            url = self.BASE_URL.format(semester, dept, number)
            
            if self.debug:
                print(f"Debug: Fetching {dept} {number} from {semester} semester")
                print(f"Debug: URL: {url}")
            
            response = self.session.get(url, timeout=10)
            
            # Check for 404 or 410 (course not offered this semester)
            if response.status_code in [404, 410]:
                if self.debug:
                    print(f"Debug: Course {course_code} not offered in {semester} (HTTP {response.status_code})")
                return None
            
            if response.status_code != 200:
                print(f"Error: HTTP {response.status_code} for {course_code} in {semester}")
                return None
            
            # Optional: Save raw HTML for debugging
            if self.debug:
                debug_filename = f"debug_{dept}_{number}_{semester}.html"
                with open(debug_filename, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"Debug: Saved raw HTML to {debug_filename}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if self.debug:
                print(f"Debug: Page title: {soup.title.string if soup.title else 'No title found'}")
                print(f"Debug: Response length: {len(response.text)} characters")
            
            # Initialize course info dictionary
            course_info = {
                'code': f"{dept} {number}",
                'title': '',
                'description': '',
                'catalog_year': '',
                'forbidden_overlaps': '',
                'distribution_requirements': '',
                'prerequisites': '',
                'permission_note': '',
                'when_offered': '',
                'satisfies_requirement': '',
                'last_terms_offered': '',
                'learning_outcomes': [],
                'semester_found': semester  # Track which semester this was found in
            }
            
            # Get catalog year from the catalog note
            catalog_note = soup.find('p', class_='catalog-note')
            if catalog_note:
                catalog_text = catalog_note.get_text(strip=True)
                # Extract the catalog year (e.g., "2024-2025" or "2025-2026")
                year_match = re.search(r'(\d{4}-\d{4})\s+Catalog', catalog_text)
                if year_match:
                    course_info['catalog_year'] = year_match.group(1)
            
            # Get course title - it's in the a tag with class title-coursedescr
            title_elem = soup.find('a', id=lambda x: x and x.startswith('dtitle-'))
            if not title_elem:
                # Fallback: look for div with class title-coursedescr
                title_div = soup.find('div', class_='title-coursedescr')
                if title_div:
                    title_elem = title_div.find('a')
            
            if title_elem:
                # The title format is "CS 1110 - Introduction to Computing: A Design..."
                # We want just the part after the dash
                full_title = title_elem.get_text(strip=True)
                if ' - ' in full_title:
                    course_info['title'] = full_title.split(' - ', 1)[1]
                else:
                    course_info['title'] = full_title
            
            if self.debug:
                print(f"Debug: Found title: {course_info['title'][:50]}..." if course_info['title'] else "Debug: No title found")
            
            # Get course description - it's in a p tag with class catalog-descr
            desc_elem = soup.find('p', class_='catalog-descr')
            if desc_elem:
                course_info['description'] = desc_elem.get_text(strip=True)
            
            if self.debug:
                print(f"Debug: Found description: {course_info['description'][:50]}..." if course_info['description'] else "Debug: No description found")
            
            # Get forbidden overlaps - in span with class catalog-forbid
            forbid_elem = soup.find('span', class_='catalog-forbid')
            if forbid_elem:
                # Remove the prompt span and get the remaining text
                prompt = forbid_elem.find('span', class_='catalog-prompt')
                if prompt:
                    prompt.extract()
                    course_info['forbidden_overlaps'] = forbid_elem.get_text(strip=True)
            
            # Get distribution requirements - in span with class catalog-attribute
            dist_elem = soup.find('span', class_='catalog-attribute')
            if dist_elem:
                # Remove the prompt span and get the remaining text
                prompt = dist_elem.find('span', class_='catalog-prompt')
                if prompt:
                    prompt.extract()
                    course_info['distribution_requirements'] = dist_elem.get_text(strip=True)
            
            # Get prerequisites - in span with class catalog-precoreq
            prereq_elem = soup.find('span', class_='catalog-precoreq')
            if prereq_elem:
                # Remove the prompt span and get the remaining text
                prompt = prereq_elem.find('span', class_='catalog-prompt')
                if prompt:
                    prompt.extract()
                    course_info['prerequisites'] = prereq_elem.get_text(strip=True)
            
            # Get permission note - in span with class catalog-permiss
            perm_elem = soup.find('span', class_='catalog-permiss')
            if perm_elem:
                # Remove the prompt span and get the remaining text
                prompt = perm_elem.find('span', class_='catalog-prompt')
                if prompt:
                    prompt.extract()
                    course_info['permission_note'] = perm_elem.get_text(strip=True)
            
            # Get when offered - in span with class catalog-when-offered
            when_elem = soup.find('span', class_='catalog-when-offered')
            if when_elem:
                # Remove the prompt span and get the remaining text
                prompt = when_elem.find('span', class_='catalog-prompt')
                if prompt:
                    prompt.extract()
                    course_info['when_offered'] = when_elem.get_text(strip=True)
            
            # Get satisfies requirement - in span with class catalog-satisfies
            satisfies_elem = soup.find('span', class_='catalog-satisfies')
            if satisfies_elem:
                # There's a nested span with class='catalog-prompt' containing "Satisfies Requirement"
                # The actual text we want comes after that span
                prompt = satisfies_elem.find('span', class_='catalog-prompt')
                if prompt:
                    # Remove the prompt span from its parent's contents and get the remaining text
                    prompt.extract()
                    satisfies_text = satisfies_elem.get_text(strip=True)
                    course_info['satisfies_requirement'] = satisfies_text
            
            # Get last terms offered - in span with class last-terms-offered
            terms_elem = soup.find('span', class_='last-terms-offered')
            if terms_elem:
                # Remove the prompt span and get the remaining text
                prompt = terms_elem.find('span', class_='catalog-prompt')
                if prompt:
                    prompt.extract()
                    course_info['last_terms_offered'] = terms_elem.get_text(strip=True)
            
            # Get learning outcomes - they're in li elements with class catalog-outcome
            outcomes = soup.find_all('li', class_='catalog-outcome')
            if outcomes:
                course_info['learning_outcomes'] = [
                    outcome.get_text(strip=True) for outcome in outcomes
                ]
            
            # Check if we actually found any course data
            if not course_info['title'] and not course_info['description']:
                if self.debug:
                    print(f"Debug: No course data found on page for {course_code} in {semester}")
                return None
            
            return course_info
            
        except Exception as e:
            print(f"Error processing {course_code} in {semester}: {str(e)}")
            return None
    
    def get_course_info(self, course_code: str, use_fallback: bool = True, max_fallbacks: int = 3) -> Optional[Dict[str, str]]:
        """
        Get information for a single course, with extended semester fallback.
        
        Args:
            course_code: Course code (e.g., "CS 1110")
            use_fallback: If True, try previous semesters if not found in current
            max_fallbacks: Maximum number of previous semesters to check (default 3)
            
        Returns:
            Dictionary with course information or None if error
        """
        # Try the current/specified semester first
        course_info = self.get_course_info_for_semester(course_code, self.semester)
        
        if course_info:
            if self.debug:
                print(f"Debug: Found {course_code} in {self.semester}")
            return course_info
        
        # If not found and fallback is enabled, try previous semesters
        if use_fallback:
            fallback_semesters = self.get_fallback_semesters(self.semester, max_fallbacks)
            checked_semesters = [self.semester]
            
            for fallback_semester in fallback_semesters:
                if self.debug:
                    print(f"Debug: {course_code} not found in {checked_semesters[-1]}, trying {fallback_semester}")
                
                course_info = self.get_course_info_for_semester(course_code, fallback_semester)
                checked_semesters.append(fallback_semester)
                
                if course_info:
                    print(f"Note: {course_code} found in {fallback_semester} (checked {', '.join(checked_semesters[:-1])} first)")
                    return course_info
            
            # If we get here, course wasn't found in any semester
            print(f"Warning: {course_code} has not been offered in: {', '.join(checked_semesters)}")
            print(f"No record found for {course_code} in the last {len(checked_semesters)} semesters")
            return None
        
        return None
    
    def format_course_output(self, course_info: Dict[str, str], include_semester_note: bool = False) -> str:
        """
        Format course information for output.
        
        Args:
            course_info: Dictionary with course information
            include_semester_note: If True, include note about which semester info was found
            
        Returns:
            Formatted string
        """
        if not course_info:
            return "Course information not available"
            
        output = []
        output.append(course_info['code'])
        output.append(course_info['title'])
        
        # Add semester note if requested and available
        if include_semester_note and 'semester_found' in course_info:
            output.append(f"[Information from {course_info['semester_found']} Class Roster]")
        
        # Add catalog year if available
        if course_info.get('catalog_year'):
            output.append(f"Course information provided by the {course_info['catalog_year']} Catalog.")
        else:
            output.append("Course information provided by the Catalog.")
        output.append("")  # Blank line
        
        # Add course description with "Course Description:" prefix
        if course_info['description']:
            output.append(f"Course Description:")
            output.append(course_info['description'])
        
        # Add prerequisites if present
        if course_info.get('prerequisites'):
            output.append(f"Prerequisites: {course_info['prerequisites']}")
        
        # Add permission note if present
        if course_info.get('permission_note'):
            output.append(f"Permission Note: {course_info['permission_note']}")
        
        # Add forbidden overlaps if present
        if course_info.get('forbidden_overlaps'):
            output.append(f"Forbidden Overlaps: {course_info['forbidden_overlaps']}")
        
        # Add distribution requirements if present
        if course_info.get('distribution_requirements'):
            output.append(f"Distribution Requirements: {course_info['distribution_requirements']}")
        
        # Add when offered if present
        if course_info.get('when_offered'):
            output.append(f"When Offered: {course_info['when_offered']}")
        
        # Add satisfies requirement if present
        if course_info.get('satisfies_requirement'):
            output.append(f"Satisfies Requirement: {course_info['satisfies_requirement']}")
        
        # Add last terms offered if present
        if course_info.get('last_terms_offered'):
            output.append(f"Last 4 Terms Offered: {course_info['last_terms_offered']}")
        
        # Add learning outcomes if present
        if course_info.get('learning_outcomes'):
            output.append("Learning Outcomes:")
            for outcome in course_info['learning_outcomes']:
                output.append(f"* {outcome}")
        
        return '\n'.join(output)
    
    def process_course_list(self, input_file: str, output_file: str, use_fallback: bool = True, max_fallbacks: int = 3):
        """
        Process a list of courses from a file and write results to output file.
        
        Args:
            input_file: Path to input file with course codes (one per line)
            output_file: Path to output file for results
            use_fallback: If True, try previous semesters if not found in current
            max_fallbacks: Maximum number of previous semesters to check (default 3)
        """
        try:
            with open(input_file, 'r') as f:
                courses = [line.strip() for line in f if line.strip()]
            
            print(f"Processing {len(courses)} courses...")
            print(f"Current semester: {self.semester}")
            if use_fallback:
                fallback_semesters = self.get_fallback_semesters(self.semester, max_fallbacks)
                print(f"Fallback semesters: {', '.join(fallback_semesters)}")
            print("-" * 50)
            
            successful = 0
            failed = []
            
            with open(output_file, 'w', encoding='utf-8') as out:
                for i, course_code in enumerate(courses, 1):
                    print(f"\nProcessing {i}/{len(courses)}: {course_code}")
                    
                    course_info = self.get_course_info(course_code, use_fallback=use_fallback, max_fallbacks=max_fallbacks)
                    
                    if course_info:
                        formatted = self.format_course_output(course_info, include_semester_note=True)
                        out.write(formatted)
                        out.write("\n\n" + "="*80 + "\n\n")
                        successful += 1
                        
                        # Note if found in different semester
                        if 'semester_found' in course_info and course_info['semester_found'] != self.semester:
                            print(f"  → Found in {course_info['semester_found']} (not in {self.semester})")
                        else:
                            print(f"  → Successfully processed")
                    else:
                        all_semesters = [self.semester] + self.get_fallback_semesters(self.semester, max_fallbacks)
                        error_msg = f"{course_code} has not been offered in: {', '.join(all_semesters)}"
                        out.write(f"{course_code}\n")
                        out.write(f"[Course not found]\n")
                        out.write(f"Course information provided by the Catalog.\n\n")
                        out.write(f"Error: {error_msg}\n\n")
                        out.write("="*80 + "\n\n")
                        failed.append(course_code)
                        print(f"  → Not found in any of the last {len(all_semesters)} semesters")
                    
                    # Be polite to the server - add a small delay between requests
                    time.sleep(0.5)
            
            print("\n" + "="*50)
            print(f"Completed! Results written to {output_file}")
            print(f"Successfully processed: {successful}/{len(courses)} courses")
            if failed:
                print(f"Failed to find: {', '.join(failed)}")
            
        except FileNotFoundError:
            print(f"Error: Could not find input file '{input_file}'")
        except Exception as e:
            print(f"Error processing course list: {str(e)}")


def main():
    """Main function to demonstrate usage."""
    print("Cornell Course Scraper Demo (Extended Fallback)")
    print("="*50)
    
    # Show automatic semester detection
    current_semester = CornellCourseScraper.get_current_semester()
    fallback_semesters = CornellCourseScraper.get_fallback_semesters(current_semester, 3)
    
    print(f"Today's date: {datetime.now().strftime('%B %d, %Y')}")
    print(f"Auto-detected semester: {current_semester}")
    print(f"Fallback semesters: {', '.join(fallback_semesters)}")
    print("="*50)
    
    # Use debug mode to see what's happening
    scraper = CornellCourseScraper(debug=True)
    
    # Example 1: Get single course information
    print("\nExample 1: Getting single course information")
    print("-" * 50)
    
    test_courses = ["CS 1110", "INFO 4120"]  # INFO 4120 might not be in Fall
    
    for course in test_courses:
        print(f"\nTesting {course}:")
        course_info = scraper.get_course_info(course)
        if course_info:
            print("\nFormatted output:")
            print(scraper.format_course_output(course_info, include_semester_note=True))
        else:
            print(f"Failed to retrieve course information for {course}")
        print("-" * 50)
    
    # Turn off debug for batch processing
    scraper.debug = False
    
    # Example 2: Process multiple courses
    print("\nExample 2: Processing multiple courses from file")
    print("-" * 50)
    
    # Create a sample input file with various courses
    sample_courses = [
        "CS 1110",
        "CS 2110", 
        "INFO 4120",  # This might only be in Spring
        "MATH 1920",
        "PHYS 1112"
    ]
    
    with open("courses_input.txt", "w") as f:
        for course in sample_courses:
            f.write(course + "\n")
    
    print("Created sample input file 'courses_input.txt'")
    
    # Process the courses
    scraper.process_course_list("courses_input.txt", "courses_output.txt")


if __name__ == "__main__":
    # Check if command line arguments are provided
    if len(sys.argv) == 1:
        # No arguments, run demo
        main()
    elif len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        # Single course query
        debug = "--debug" in sys.argv
        no_fallback = "--no-fallback" in sys.argv
        
        # Check for max fallbacks override
        max_fallbacks = 3  # Default
        for i, arg in enumerate(sys.argv):
            if arg == "--max-fallbacks" and i + 1 < len(sys.argv):
                try:
                    max_fallbacks = int(sys.argv[i + 1])
                except ValueError:
                    print(f"Warning: Invalid max-fallbacks value '{sys.argv[i + 1]}', using default (3)")
        
        # Check for semester override
        semester = None
        for i, arg in enumerate(sys.argv):
            if arg == "--semester" and i + 1 < len(sys.argv):
                semester = sys.argv[i + 1]
                break
        
        scraper = CornellCourseScraper(semester=semester, debug=debug)
        course_info = scraper.get_course_info(sys.argv[1], use_fallback=not no_fallback, max_fallbacks=max_fallbacks)
        
        if course_info:
            print(scraper.format_course_output(course_info, include_semester_note=True))
        else:
            print(f"Failed to retrieve information for {sys.argv[1]}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "--file":
        # File processing mode
        debug = "--debug" in sys.argv
        no_fallback = "--no-fallback" in sys.argv
        
        # Check for max fallbacks override
        max_fallbacks = 3  # Default
        for i, arg in enumerate(sys.argv):
            if arg == "--max-fallbacks" and i + 1 < len(sys.argv):
                try:
                    max_fallbacks = int(sys.argv[i + 1])
                except ValueError:
                    print(f"Warning: Invalid max-fallbacks value '{sys.argv[i + 1]}', using default (3)")
        
        # Check for semester override
        semester = None
        for i, arg in enumerate(sys.argv):
            if arg == "--semester" and i + 1 < len(sys.argv):
                semester = sys.argv[i + 1]
                break
        
        scraper = CornellCourseScraper(semester=semester, debug=debug)
        
        input_file = sys.argv[2]
        # Find output file (skip flags and semester codes)
        output_file = None
        skip_next = False
        for i, arg in enumerate(sys.argv[3:], start=3):
            if skip_next:
                skip_next = False
                continue
            if arg in ["--semester", "--max-fallbacks"]:
                skip_next = True
                continue
            if not arg.startswith("--") and not re.match(r'^(FA|SP|SU|WI)\d{2}$', arg):
                output_file = arg
                break
        
        if not output_file:
            output_file = "courses_output.txt"
        
        scraper.process_course_list(input_file, output_file, use_fallback=not no_fallback, max_fallbacks=max_fallbacks)
    else:
        print("Cornell Course Scraper (Extended Fallback)")
        print("="*50)
        print("Usage:")
        print("  python script.py                                    # Run demo")
        print("  python script.py 'CS 1110' [options]               # Get single course")
        print("  python script.py --file input.txt [output.txt] [options]  # Process file")
        print()
        print("Options:")
        print("  --debug              Show detailed debug information")
        print("  --no-fallback        Don't check previous semesters if not found")
        print("  --semester TERM      Override semester (e.g., FA25, SP26)")
        print("  --max-fallbacks N    Maximum number of previous semesters to check (default: 3)")
        print()
        print("Examples:")
        print("  python script.py 'CS 1110'")
        print("  python script.py 'INFO 4120' --debug")
        print("  python script.py 'INFO 4120' --max-fallbacks 5")
        print("  python script.py --file courses.txt results.txt")
        print("  python script.py --file courses.txt --semester SP25 --debug")
        print()
        current = CornellCourseScraper.get_current_semester()
        fallbacks = CornellCourseScraper.get_fallback_semesters(current, 3)
        print(f"Current auto-detected semester: {current}")
        print(f"Default fallback semesters: {', '.join(fallbacks)}")