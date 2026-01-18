import os
import json
import markdown
from bs4 import BeautifulSoup
import re
import yaml

def extract_text_from_markdown(markdown_content):
    """
    Converts Markdown to HTML, then removes HTML tags,
    also removes Frontmatter, code blocks, MkDocs macros and service comments,
    leaving maximally clean text for AI training.
    Preserves Markdown tables in readable format.
    """
    # 1. Remove Frontmatter using YAML parser
    lines = markdown_content.splitlines()
    content_without_frontmatter = markdown_content

    # Check if file starts with frontmatter (---)
    if lines and lines[0].strip() == '---':
        # Look for closing ---
        end_frontmatter = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                end_frontmatter = i
                break

        if end_frontmatter > 0:
            # Remove frontmatter
            content_without_frontmatter = '\\n'.join(lines[end_frontmatter + 1:])

    # Additionally remove any remaining frontmatter-like lines
    lines = content_without_frontmatter.splitlines()
    cleaned_lines = []

    for line in lines:
        stripped_line = line.strip()
        # Skip lines with metadata or Notion URLs - use simple string matching
        if stripped_line.startswith('https://www.notion.so/n8n/Frontmatter-'):
            continue
        if any(stripped_line.startswith(f"{key}:") for key in ['title', 'description', 'contentType', 'tags', 'hide', 'aliases', 'priority', 'redirect_from']):
            continue
        cleaned_lines.append(line)

    cleaned_markdown_content = '\\n'.join(cleaned_lines)

    # 2. Remove code blocks (```)
    try:
        cleaned_markdown_content = re.sub(r'```.*?```', '', cleaned_markdown_content, flags=re.DOTALL)
    except:
        pass

    # 3. Remove inline code in backticks, but preserve content
    try:
        cleaned_markdown_content = re.sub(r'`([^`]+)`', r'\\1', cleaned_markdown_content)
    except:
        pass

    # 4. Remove MkDocs macros
    try:
        cleaned_markdown_content = re.sub(r'\\[\\[.*?\\]\\]', '', cleaned_markdown_content)
    except:
        pass

    # 5. Remove MkDocs Material service blocks
    try:
        cleaned_markdown_content = re.sub(r'///.*?///', '', cleaned_markdown_content, flags=re.DOTALL)
    except:
        pass

    # 6. Remove HTML comments
    try:
        cleaned_markdown_content = re.sub(r'<!--.*?-->', '', cleaned_markdown_content, flags=re.DOTALL)
    except:
        pass

    # 7. Remove Snippet markers
    try:
        cleaned_markdown_content = re.sub(r'--8<--\\s*".*?"', '', cleaned_markdown_content)
    except:
        pass

    # 8. Remove all URL links (including Notion and regular HTTP/HTTPS)
    try:
        cleaned_markdown_content = re.sub(r'https?://[^\\s\\)]+', '', cleaned_markdown_content)
    except:
        pass

    # 9. Remove Markdown links [text](url), but preserve text
    try:
        cleaned_markdown_content = re.sub(r'\\[([^\\]]*)\\]\\([^\\)]*\\)', r'\\1', cleaned_markdown_content)
    except:
        pass

    # 10. Remove reference-style links [text][ref]
    try:
        cleaned_markdown_content = re.sub(r'\\[([^\\]]*)\\]\\[[^\\]]*\\]', r'\\1', cleaned_markdown_content)
    except:
        pass

    # 11. Remove link definitions [ref]: url - use simple string matching
    lines_after_links = []
    for line in cleaned_markdown_content.split('\\n'):
        if line.strip().startswith('[') and ']: ' in line:
            continue
        lines_after_links.append(line)
    cleaned_markdown_content = '\\n'.join(lines_after_links)

    # 12. Preserve and format tables
    # Find all tables using simple pattern matching instead of complex regex
    table_placeholders = {}
    processed_content = cleaned_markdown_content
    
    # Look for lines that start with pipe character (table rows)
    lines = processed_content.split('\\n')
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith('|'):
            # Found a table, collect all consecutive pipe lines
            table_lines = []
            start_i = i
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            
            if table_lines:
                table_text = '\\n'.join(table_lines)
                placeholder = f"__TABLE_PLACEHOLDER_{len(table_placeholders)}__"
                formatted_table = format_markdown_table(table_text)
                table_placeholders[placeholder] = formatted_table
                
                # Replace the table in content
                processed_content = processed_content.replace(table_text, placeholder, 1)
        else:
            i += 1
    
    cleaned_markdown_content = processed_content

    # 13. Convert remaining Markdown to HTML and extract text
    try:
        html = markdown.markdown(cleaned_markdown_content, extensions=['tables'])
        soup = BeautifulSoup(html, 'html.parser')

        # Remove scripts and styles
        for script_or_style in soup(['script', 'style']):
            script_or_style.extract()

        text = soup.get_text()
    except:
        text = cleaned_markdown_content

    # 14. Restore tables in readable format
    for placeholder, table in table_placeholders.items():
        text = text.replace(placeholder, table)

    # 15. Final cleanup
    # Remove excessive blank lines and whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Join lines with one blank line between paragraphs
    final_text = '\\n'.join(lines)

    # Remove multiple line breaks - safe simple pattern
    try:
        final_text = re.sub(r'\\n{3,}', '\\n\\n', final_text)
    except:
        pass

    return final_text.strip()


def format_markdown_table(table_text):
    """
    Formats Markdown table into a more readable text format
    """
    lines = [line.strip() for line in table_text.strip().split('\\n') if line.strip()]
    if len(lines) < 1:
        return ""

    # Remove separator line with |---|---|
    header_line = lines[0] if lines else ""
    data_lines = []

    for line in lines[1:]:
        # Skip table separator lines - use simple character check instead of regex
        is_separator = all(c in '|\\t -:' for c in line)
        if not is_separator and line.strip():
            data_lines.append(line)

    # If no headers or data, just return cleaned text
    if not header_line.startswith('|'):
        return table_text.replace('|', ' ').strip()

    # Extract headers
    headers = [cell.strip() for cell in header_line.split('|')[1:-1] if cell.strip()]

    # Format table
    formatted_lines = []

    # Add data rows
    for line in data_lines:
        if line.startswith('|') and line.endswith('|'):
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            if cells and any(cell for cell in cells):  # Check that row is not empty
                row_text = []
                for i, cell in enumerate(cells):
                    if cell:
                        if i < len(headers) and headers[i]:
                            row_text.append(f"{headers[i]}: {cell}")
                        else:
                            row_text.append(cell)
                if row_text:
                    formatted_lines.append(" | ".join(row_text))

    # If table is empty, return simple text
    if not formatted_lines:
        return table_text.replace('|', ' ').strip()

    return '\\n'.join(formatted_lines)


def process_documentation(docs_base_path, output_json_path):
    """
    Walks through all Markdown files in the specified directory,
    extracts cleaned text and saves it to JSON.
    """
    documentation_data = []

    print(f"Starting to process documents from: {docs_base_path}")
    processed_count = 0

    for root, _, files in os.walk(docs_base_path):
        for file_name in files:
            if file_name.endswith('.md'):
                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(file_path, docs_base_path)

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()

                    clean_text = extract_text_from_markdown(markdown_content)

                    if clean_text and len(clean_text.strip()) > 50:  # Minimum length to save
                        documentation_data.append({
                            "file_path": relative_path,
                            "content": clean_text
                        })
                        processed_count += 1
                        print(f"[OK] Processed file: {relative_path} ({len(clean_text)} characters)")
                    else:
                        print(f"[SKIP] Skipped file (too little content): {relative_path}")

                except Exception as e:
                    print(f"[ERR] Error processing file {file_path}: {e}")

    if documentation_data:
        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(documentation_data, f, ensure_ascii=False, indent=2)
            print(f"\\n[SUCCESS] All cleaned data successfully saved to: {output_json_path}")
            print(f"[STATS] Statistics:")
            print(f" - Total documents processed: {processed_count}")
            print(f" - Total JSON file size: {os.path.getsize(output_json_path) / 1024 / 1024:.2f} MB")
        except Exception as e:
            print(f"[ERR] Error saving JSON file {output_json_path}: {e}")
    else:
        print("\\n[WARN] No data to save. Check the documentation path and file contents.")


if __name__ == "__main__":
    # Use relative paths instead of hardcoded user paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    docs_directory = os.path.join(script_dir, 'docs')
    output_file = os.path.join(script_dir, 'n8n_documentation_cleaned_improved.json')

    if not os.path.isdir(docs_directory):
        print(f"[ERR] Error: Directory '{docs_directory}' not found. Please check the path.")
    else:
        process_documentation(docs_directory, output_file)