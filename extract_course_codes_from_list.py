import re

def extract_unique_courses(input_file_path, output_file_path):
    """
    Extracts unique course codes from an input text file, sorts them,
    and writes them to an output text file.

    Args:
        input_file_path (str): The path to the text file to read from.
        output_file_path (str): The path to the text file to write to.
    """
    try:
        with open(input_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"Error: The file '{input_file_path}' was not found.")
        return

    # Regex to find patterns like 'DEPT 1234' (e.g., 'INFO 3450', 'CS 4740')
    # [A-Z]+ matches one or more uppercase letters for the department code.
    # \d{4} matches exactly four digits for the course number.
    course_code_pattern = r'[A-Z]+ \d{4}'
    
    # Find all occurrences matching the pattern
    found_courses = re.findall(course_code_pattern, content)
    
    # Use a set to get unique course codes and then convert back to a list
    unique_courses = sorted(list(set(found_courses)))
    
    # Write the sorted, unique course codes to the output file
    with open(output_file_path, 'w', encoding='utf-8') as file:
        for course in unique_courses:
            file.write(course + '\n')
            
    print(f"Successfully extracted {len(unique_courses)} unique course codes.")
    print(f"Results have been saved to '{output_file_path}'.")

# --- Execution ---
# Name of the file containing the course list
input_filename = 'input_courses.txt'

# Name for the new file that will be created
output_filename = 'unique_courses.txt'

# Run the function
extract_unique_courses(input_filename, output_filename)