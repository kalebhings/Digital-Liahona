from flask import Flask, request, jsonify
from neo4j import GraphDatabase
import ollama
import os
import re
import unicodedata
import json
from typing import List, Dict, Tuple, Any

app = Flask(__name__)

# --- Connection Details ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_MODEL = "nomic-embed-text"
OLLAMA_LLM_MODEL = "llama3.2"  # Model for text generation and selection
# OLLAMA_LLM_MODEL = "gemma3:12b"  # Model for text generation and selection

# --- Neo4j Driver ---
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Successfully connected to Neo4j.")
except Exception as e:
    print(f"Failed to connect to Neo4j: {e}")
    driver = None

def get_db_session():
    """Gets a session from the Neo4j driver."""
    if driver:
        return driver.session()
    return None

def clean_text(text: str) -> str:
    """
    Cleans text by removing Unicode escape sequences, mojibake, and normalizing characters.
    """
    if not text:
        return text
    
    # Handle specific problematic sequences first
    # Replace \x80\x9c with left double quote
    text = text.replace('\\x80\\x9c', '"')
    # Replace \x80\x9d with right double quote  
    text = text.replace('\\x80\\x9d', '"')
    # Replace \x80\x99 with right single quote
    text = text.replace('\\x80\\x99', "'")
    
    # First, handle Unicode escape sequences more aggressively
    try:
        # Convert Unicode escape sequences to actual characters
        text = text.encode('utf-8').decode('unicode_escape')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    
    # Handle mojibake (mis-decoded UTF-8)
    try:
        # Try to fix mojibake by re-encoding and decoding
        b = text.encode("latin1")
        text = b.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    # Remove specific problematic Unicode sequences (but be more careful)
    text = re.sub(r'\\u[0-9a-fA-F]{4}', '', text)  # Remove \uXXXX sequences
    text = re.sub(r'\\x[0-9a-fA-F]{2}', '', text)  # Remove \xXX sequences
    
    # Normalize Unicode characters
    text = unicodedata.normalize("NFKD", text)
    
    # Remove combining diacritical marks
    text = re.sub(r"[\u0300-\u036f]", "", text)
    
    # Replace non-breaking spaces and other problematic characters
    text = text.replace("\u00a0", " ")
    text = text.replace("\\/", "/")
    
    # Remove other problematic characters but preserve quotes
    text = re.sub(r'[\u0080-\u009F]', '', text)  # Remove control characters
    
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()

def embed(text: str):
    """Generates an embedding for the given text using Ollama."""
    try:
        return ollama.embeddings(model=OLLAMA_MODEL, prompt=text)["embedding"]
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

def understand_user_intent(user_message: str) -> List[str]:
    """
    Uses LLM to understand user intent and generate multiple search queries.
    This implements multi-query retrieval to improve recall on metaphorical/idiomatic requests.
    """
    try:
        prompt = f"""You are a helpful assistant that understands user questions about LDS gospel topics and converts them into effective search queries.

User Question: {user_message}

Your task is to:
1. Understand the user's intent (what they're really asking about)
2. Generate 1-3 different search queries that would help find relevant LDS scriptures and conference talks

Consider:
- Direct keywords from the question
- Related gospel concepts and principles
- Different ways to express the same idea
- Broader and narrower interpretations

Return ONLY a JSON array of search queries, like this:
["query 1", "query 2", "query 3"]

Example for "What should I build my foundation on?":
["foundation of faith", "building on Christ", "spiritual foundation"]

Example for "How do I find peace?":
["peace through Christ", "finding inner peace", "peace in trials"]"""

        response = ollama.chat(model=OLLAMA_LLM_MODEL, messages=[{
            'role': 'user',
            'content': prompt
        }])
        
        llm_response = response['message']['content']
        print(f"Intent understanding response: {llm_response}")
        
        # Try to extract JSON array from response
        try:
            # Look for JSON array in the response
            json_match = re.search(r'\[.*?\]', llm_response, re.DOTALL)
            if json_match:
                queries = json.loads(json_match.group())
                if isinstance(queries, list) and len(queries) > 0:
                    return queries
        except (json.JSONDecodeError, AttributeError):
            pass
        
        # Fallback: return the original message as a single query
        return [user_message]
        
    except Exception as e:
        print(f"Error in intent understanding: {e}")
        return [user_message]

def detect_relevant_topics(user_message: str) -> List[str]:
    """
    Uses LLM to detect relevant LDS gospel topics for the user's question.
    """
    try:
        # Load a sample of topics to give the LLM context
        topics_sample = [
            "Faith", "Repentance", "Baptism", "Holy Ghost", "Prayer", "Scripture Study",
            "Temple", "Family", "Service", "Charity", "Forgiveness", "Hope", "Love",
            "Obedience", "Covenants", "Priesthood", "Prophets", "Atonement", "Resurrection",
            "Eternal Life", "Heavenly Father", "Jesus Christ", "Holy Spirit", "Gospel",
            "Testimony", "Conversion", "Endure to the End", "Grace", "Mercy", "Justice"
        ]
        
        prompt = f"""You are a helpful assistant that identifies relevant LDS gospel topics for user questions.

User Question: {user_message}

Available LDS Gospel Topics (sample):
{', '.join(topics_sample)}

Identify the 3 most relevant gospel topics for this question. Consider:
- Direct matches to the question
- Related gospel principles
- Broader themes that might apply

Return ONLY a JSON array of topic names, like this:
["topic1", "topic2", "topic3"]

Example for "How do I find peace?":
["Peace", "Prayer", "Faith"]

Example for "What should I build my foundation on?":
["Faith", "Foundation", "Jesus Christ"]"""

        response = ollama.chat(model=OLLAMA_LLM_MODEL, messages=[{
            'role': 'user',
            'content': prompt
        }])
        
        llm_response = response['message']['content']
        print(f"Topic detection response: {llm_response}")
        
        # Try to extract JSON array from response
        try:
            json_match = re.search(r'\[.*?\]', llm_response, re.DOTALL)
            if json_match:
                topics = json.loads(json_match.group())
                if isinstance(topics, list) and len(topics) > 0:
                    return topics
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return []
        
    except Exception as e:
        print(f"Error in topic detection: {e}")
        return []

def hybrid_search(session, queries: List[str], detected_topics: List[str], user_query: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Performs hybrid search combining:
    1. Vector similarity search with multiple queries (including original user query)
    2. Topic-based search using MENTIONS relationships
    """
    all_verses = []
    all_paragraphs = []
    
    # Add the original user query to the search queries
    all_queries = [user_query] + queries
    
    # 1. Vector similarity search for each query (including original user query)
    for query in all_queries:
        query_embedding = embed(query)
        if not query_embedding:
            continue
            
        # Vector search for verses
        verse_query = """
        CALL db.index.vector.queryNodes('verse_embedding', 3, $embedding) YIELD node AS verse, score AS v_score
        WITH verse, v_score
        OPTIONAL MATCH (verse)<-[:CONTAINS]-(chapter)<-[:CONTAINS]-(book)
        WITH verse.text AS verse_text, v_score, book.title AS book_title, chapter.number AS chapter_number, verse.number AS verse_number
        RETURN verse_text AS text, v_score AS score, book_title + ' ' + chapter_number + ':' + verse_number AS source
        """
        
        # Vector search for paragraphs
        paragraph_query = """
        CALL db.index.vector.queryNodes('paragraph_embedding', 3, $embedding) YIELD node AS paragraph, score AS p_score
        WITH paragraph, p_score
        OPTIONAL MATCH (paragraph)<-[:CONTAINS]-(talk)
        RETURN paragraph.text AS text, p_score AS score, talk.title AS source
        """
        
        try:
            verse_results = session.run(verse_query, embedding=query_embedding)
            for record in verse_results:
                all_verses.append({
                    'text': clean_text(record['text']),
                    'source': clean_text(record['source']),
                    'score': record['score'],
                    'query': query
                })
                
            paragraph_results = session.run(paragraph_query, embedding=query_embedding)
            for record in paragraph_results:
                all_paragraphs.append({
                    'text': clean_text(record['text']),
                    'source': clean_text(record['source']),
                    'score': record['score'],
                    'query': query
                })
        except Exception as e:
            print(f"Error in vector search for query '{query}': {e}")
    
    # 2. Topic-based search
    if detected_topics:
        topic_verse_query = """
        MATCH (tp:Topic)<-[:MENTIONS]-(v:Verse)
        WHERE tp.name IN $topics
        OPTIONAL MATCH (v)<-[:CONTAINS]-(chapter)<-[:CONTAINS]-(book)
        WITH v.text AS verse_text, 0.8 AS topic_score, book.title AS book_title, chapter.number AS chapter_number, v.number AS verse_number
        RETURN verse_text AS text, topic_score AS score, book_title + ' ' + chapter_number + ':' + verse_number AS source
        LIMIT 5
        """
        
        topic_paragraph_query = """
        MATCH (tp:Topic)<-[:MENTIONS]-(t:Talk)-[:CONTAINS]->(p:Paragraph)
        WHERE tp.name IN $topics
        RETURN p.text AS text, 0.8 AS score, t.title AS source
        LIMIT 5
        """
        
        try:
            topic_verse_results = session.run(topic_verse_query, topics=detected_topics)
            for record in topic_verse_results:
                all_verses.append({
                    'text': clean_text(record['text']),
                    'source': clean_text(record['source']),
                    'score': record['score'],
                    'query': f"topic:{', '.join(detected_topics)}"
                })
                
            topic_paragraph_results = session.run(topic_paragraph_query, topics=detected_topics)
            for record in topic_paragraph_results:
                all_paragraphs.append({
                    'text': clean_text(record['text']),
                    'source': clean_text(record['source']),
                    'score': record['score'],
                    'query': f"topic:{', '.join(detected_topics)}"
                })
        except Exception as e:
            print(f"Error in topic search: {e}")
        
    # Remove duplicates and sort by score
    unique_verses = {}
    for verse in all_verses:
        key = (verse['text'], verse['source'])
        if key not in unique_verses or verse['score'] > unique_verses[key]['score']:
            unique_verses[key] = verse
    
    unique_paragraphs = {}
    for paragraph in all_paragraphs:
        key = (paragraph['text'], paragraph['source'])
        if key not in unique_paragraphs or paragraph['score'] > unique_paragraphs[key]['score']:
            unique_paragraphs[key] = paragraph
    
    # Sort by score and return top results
    sorted_verses = sorted(unique_verses.values(), key=lambda x: x['score'], reverse=True)[:10]
    sorted_paragraphs = sorted(unique_paragraphs.values(), key=lambda x: x['score'], reverse=True)[:10]
    
    return sorted_verses, sorted_paragraphs

def select_best_results_with_llm(user_message: str, verses: list, paragraphs: list, num_verses: int = 2, num_paragraphs: int = 2):
    """
    Uses an LLM to select the best verses and paragraphs based on relevance to the user's question.
    Also provides explanations for how each selection applies to the question.
    """
    try:
        # Clean the text before sending to LLM
        cleaned_verses = []
        for v in verses:
            cleaned_verses.append({
                'text': clean_text(v['text']),
                'source': clean_text(v['source']),
                'score': v['score']
            })
        
        cleaned_paragraphs = []
        for p in paragraphs:
            cleaned_paragraphs.append({
                'text': clean_text(p['text']),
                'source': clean_text(p['source']),
                'score': p['score']
            })
        
        # Format the candidates for the LLM
        verses_text = "\n".join([f"VERSE {i+1}: {v['text']} (Source: {v['source']})" for i, v in enumerate(cleaned_verses)])
        paragraphs_text = "\n".join([f"PARAGRAPH {i+1}: {p['text']} (Source: {p['source']})" for i, p in enumerate(cleaned_paragraphs)])
        
        prompt = f"""You are a helpful assistant that selects the most relevant religious texts to answer a user's question and explains how each applies.

        User Question: {user_message}

        Available Verses:
        {verses_text}

        Available Conference Paragraphs:
        {paragraphs_text}

        Please select the {num_verses} most relevant verses and {num_paragraphs} most relevant conference paragraphs that best answer the user's question. Consider:
        1. Direct relevance to the question
        2. Clarity and comprehensibility
        3. Doctrinal accuracy
        4. Practical application

        For each selected verse, provide a one-sentence explanation of how it applies to the user's question.
        For each selected conference paragraph, provide a one-sentence explanation of how it applies to the user's question.

        Respond in this exact format:
        BEST VERSES: [comma-separated numbers]
        VERSE EXPLANATIONS: [one sentence per verse, comma-separated]
        BEST PARAGRAPHS: [comma-separated numbers]
        PARAGRAPH EXPLANATIONS: [one sentence per paragraph, comma-separated]

        For example:
        BEST VERSES: 1, 3
        VERSE EXPLANATIONS: This verse teaches about building on a solid spiritual foundation, This verse shows how faith provides strength in trials
        BEST PARAGRAPHS: 2, 4
        PARAGRAPH EXPLANATIONS: This talk emphasizes the importance of prayer in finding peace, This talk explains how service brings inner peace"""

        # Get LLM response
        response = ollama.chat(model=OLLAMA_LLM_MODEL, messages=[{
            'role': 'user',
            'content': prompt
        }])
        
        llm_response = response['message']['content']
        print(f"LLM Selection Response: {llm_response}")
        
        # Parse the response
        selected_verses = []
        selected_paragraphs = []
        verse_explanations = []
        paragraph_explanations = []
        
        lines = llm_response.split('\n')
        for line in lines:
            if line.startswith('BEST VERSES:'):
                verse_numbers = [int(x.strip()) for x in line.split(':')[1].strip().split(',')]
                selected_verses = [cleaned_verses[i-1] for i in verse_numbers if 1 <= i <= len(cleaned_verses)]
            elif line.startswith('VERSE EXPLANATIONS:'):
                explanations = line.split(':')[1].strip().split(',')
                verse_explanations = [exp.strip() for exp in explanations]
            elif line.startswith('BEST PARAGRAPHS:'):
                paragraph_numbers = [int(x.strip()) for x in line.split(':')[1].strip().split(',')]
                selected_paragraphs = [cleaned_paragraphs[i-1] for i in paragraph_numbers if 1 <= i <= len(cleaned_paragraphs)]
            elif line.startswith('PARAGRAPH EXPLANATIONS:'):
                explanations = line.split(':')[1].strip().split(',')
                paragraph_explanations = [exp.strip() for exp in explanations]
        
        # Add explanations to the selected items
        for i, verse in enumerate(selected_verses):
            if i < len(verse_explanations):
                verse['explanation'] = verse_explanations[i]
            else:
                verse['explanation'] = "This verse provides relevant guidance for your question."
        
        for i, paragraph in enumerate(selected_paragraphs):
            if i < len(paragraph_explanations):
                paragraph['explanation'] = paragraph_explanations[i]
            else:
                paragraph['explanation'] = "This conference insight offers valuable perspective on your question."
        
        return selected_verses, selected_paragraphs
        
    except Exception as e:
        print(f"Error in LLM selection: {e}")
        # Fallback: return top results by score with cleaned text and default explanations
        cleaned_verses = [{'text': clean_text(v['text']), 'source': clean_text(v['source']), 'score': v['score'], 'explanation': 'This verse provides relevant guidance for your question.'} for v in verses]
        cleaned_paragraphs = [{'text': clean_text(p['text']), 'source': clean_text(p['source']), 'score': p['score'], 'explanation': 'This conference insight offers valuable perspective on your question.'} for p in paragraphs]
        return cleaned_verses[:num_verses], cleaned_paragraphs[:num_paragraphs]

def get_chapter_info(session, verse_source: str) -> dict:
    """
    Extracts chapter information from a verse source string.
    Returns chapter details for creating read-only chapter links.
    """
    try:
        # Parse verse source (e.g., "Book of Mormon 1 Nephi 1:1")
        parts = verse_source.split()
        if len(parts) >= 4:
            # Handle cases like "Book of Mormon 1 Nephi 1:1"
            if parts[0] == "Book" and parts[1] == "of" and parts[2] == "Mormon":
                book = " ".join(parts[3:-1])  # "1 Nephi"
                chapter_verse = parts[-1]  # "1:1"
            else:
                # Handle other cases like "New Testament Matthew 1:1"
                book = " ".join(parts[1:-1])  # "Matthew"
                chapter_verse = parts[-1]  # "1:1"
            
            if ":" in chapter_verse:
                chapter_num = chapter_verse.split(":")[0]
                return {
                    "book": book,
                    "chapter": chapter_num,
                    "full_reference": f"{book} {chapter_num}",
                    "chapter_url": f"/chapter/{book.replace(' ', '-').lower()}/{chapter_num}"
                }
    except Exception as e:
        print(f"Error parsing chapter info from {verse_source}: {e}")
    
    return None

def get_related_content(session, user_query: str, selected_verses: list, selected_paragraphs: list) -> dict:
    """
    Finds additional related content based on the user's query and selected results.
    Returns related verses, talks, and topics.
    """
    related_content = {
        "related_verses": [],
        "related_talks": [],
        "related_topics": []
    }
    
    try:
        # Get related verses from the same books/chapters
        if selected_verses:
            # Extract book names from selected verses
            books = set()
            for verse in selected_verses:
                source = verse.get('source', '')
                if source:
                    parts = source.split()
                    if len(parts) >= 3:
                        if parts[0] == "Book" and parts[1] == "of" and parts[2] == "Mormon":
                            book = " ".join(parts[3:])
                        else:
                            book = " ".join(parts[1:])
                        books.add(book.split()[0])  # Get first word of book name
            
            # Find related verses from same books
            for book in list(books)[:2]:  # Limit to 2 books
                related_query = """
                MATCH (v:Verse)<-[:CONTAINS]-(c:Chapter)<-[:CONTAINS]-(b:Book)
                WHERE b.title CONTAINS $book
                WITH v, b, c
                ORDER BY c.number, v.number
                LIMIT 3
                RETURN v.text AS text, b.title + ' ' + c.number + ':' + v.number AS source
                """
                
                results = session.run(related_query, book=book)
                for record in results:
                    if record['source'] not in [v['source'] for v in selected_verses]:
                        related_content["related_verses"].append({
                            "text": clean_text(record['text']),
                            "source": clean_text(record['source']),
                            "chapter_info": get_chapter_info(session, record['source'])
                        })
        
        # Get related talks from same speakers or similar topics
        if selected_paragraphs:
            # Extract speaker names from selected talks
            speakers = set()
            for paragraph in selected_paragraphs:
                source = paragraph.get('source', '')
                if source:
                    # Try to find speaker for this talk
                    speaker_query = """
                    MATCH (s:Speaker)-[:GAVE]->(t:Talk)
                    WHERE t.title = $title
                    RETURN s.name AS speaker
                    LIMIT 1
                    """
                    result = session.run(speaker_query, title=source)
                    speaker_record = result.single()
                    if speaker_record:
                        speakers.add(speaker_record['speaker'])
            
            # Find related talks from same speakers
            for speaker in list(speakers)[:2]:  # Limit to 2 speakers
                related_talk_query = """
                MATCH (s:Speaker {name: $speaker})-[:GAVE]->(t:Talk)-[:CONTAINS]->(p:Paragraph)
                WHERE t.title <> $exclude_title
                WITH t, p
                ORDER BY t.year DESC, t.season
                LIMIT 2
                RETURN p.text AS text, t.title AS source, t.year AS year
                """
                
                for paragraph in selected_paragraphs:
                    results = session.run(related_talk_query, speaker=speaker, exclude_title=paragraph['source'])
                    for record in results:
                        if record['source'] not in [p['source'] for p in selected_paragraphs]:
                            related_content["related_talks"].append({
                                "text": clean_text(record['text']),
                                "source": clean_text(record['source']),
                                "year": record['year']
                            })
        
        # Get related topics based on user query
        detected_topics = detect_relevant_topics(user_query)
        if detected_topics:
            for topic in detected_topics[:3]:  # Limit to 3 topics
                topic_query = """
                MATCH (tp:Topic {name: $topic})
                OPTIONAL MATCH (tp)-[:MENTIONS]->(v:Verse)
                OPTIONAL MATCH (tp)-[:MENTIONS]->(t:Talk)
                RETURN tp.name AS topic_name, 
                       count(v) AS verse_count,
                       count(t) AS talk_count
                """
                
                result = session.run(topic_query, topic=topic)
                topic_record = result.single()
                if topic_record and (topic_record['verse_count'] > 0 or topic_record['talk_count'] > 0):
                    related_content["related_topics"].append({
                        "name": topic_record['topic_name'],
                        "verse_count": topic_record['verse_count'],
                        "talk_count": topic_record['talk_count'],
                        "topic_url": f"/topic/{topic_record['topic_name'].replace(' ', '-').lower()}"
                    })
    
    except Exception as e:
        print(f"Error getting related content: {e}")
    
    return related_content

def format_response_with_links(user_message: str, selected_verses: list, selected_paragraphs: list, session) -> dict:
    """
    Formats the response with chapter links and related content references.
    """
    # Get chapter information for verses
    verses_with_links = []
    for verse in selected_verses:
        chapter_info = get_chapter_info(session, verse['source'])
        verses_with_links.append({
            "text": verse['text'],
            "source": verse['source'],
            "chapter_info": chapter_info,
            "explanation": verse.get('explanation', 'This verse provides relevant guidance for your question.')
        })
    
    # Get related content
    related_content = get_related_content(session, user_message, selected_verses, selected_paragraphs)
    
    # Format the main reply with better spacing
    reply_parts = ["Here are some things that might help:\n"]
    
    # Add selected verses with chapter links and explanations
    if verses_with_links:
        reply_parts.append("📖 **Scripture References:**\n")
        for i, item in enumerate(verses_with_links, 1):
            chapter_link = ""
            if item['chapter_info']:
                chapter_link = f" [📖 Read Full Chapter]({item['chapter_info']['chapter_url']})"
            explanation = item.get('explanation', 'This verse provides relevant guidance for your question.')
            reply_parts.append(f"**{i}.** From \"{item['source']}\":\n")
            reply_parts.append(f"   \"{item['text']}\"{chapter_link}\n")
            reply_parts.append(f"   💡 {explanation}\n")
    
    # Add selected paragraphs with explanations
    if selected_paragraphs:
        if verses_with_links:
            reply_parts.append("\n")  # Add spacing between sections
        reply_parts.append("🎤 **Conference Insights:**\n")
        for i, item in enumerate(selected_paragraphs, 1):
            explanation = item.get('explanation', 'This conference insight offers valuable perspective on your question.')
            reply_parts.append(f"**{i}.** From \"{item['source']}\":\n")
            reply_parts.append(f"   \"{item['text']}\"\n")
            reply_parts.append(f"   💡 {explanation}\n")
    
    # Add related content section
    if (related_content["related_verses"] or 
        related_content["related_talks"] or 
        related_content["related_topics"]):
        
        if verses_with_links or selected_paragraphs:
            reply_parts.append("\n")  # Add spacing before related content
        
        reply_parts.append("🔗 **Related Content:**\n")
        
        if related_content["related_topics"]:
            reply_parts.append("\n📚 **Related Topics:**\n")
            for topic in related_content["related_topics"][:3]:
                reply_parts.append(f"• {topic['name']} ({topic['verse_count']} verses, {topic['talk_count']} talks) [Explore]({topic['topic_url']})\n")
        
        if related_content["related_verses"]:
            reply_parts.append("\n📖 **Additional Scripture References:**\n")
            for verse in related_content["related_verses"][:2]:
                chapter_link = ""
                if verse['chapter_info']:
                    chapter_link = f" [📖 Read Chapter]({verse['chapter_info']['chapter_url']})"
                reply_parts.append(f"• {verse['source']}: \"{verse['text'][:100]}...\"{chapter_link}\n")
        
        if related_content["related_talks"]:
            reply_parts.append("\n🎤 **Related Conference Talks:**\n")
            for talk in related_content["related_talks"][:2]:
                reply_parts.append(f"• {talk['source']} ({talk['year']}): \"{talk['text'][:100]}...\"\n")
    
    return {
        "reply": "".join(reply_parts).strip(),
        "related_content": related_content,
        "verses_with_links": verses_with_links
    }

@app.route('/chat', methods=['POST'])
def chat():
    """
    Handles chat requests from the frontend with enhanced search capabilities.
    """
    data = request.get_json()
    user_message = data.get('message')
    print(f"User message: {user_message}")
    print(f"Driver: {driver}")

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    if not driver:
        return jsonify({'error': 'Database connection not available'}), 500

    # 1. Understand user intent and generate multiple search queries
    search_queries = understand_user_intent(user_message)
    print(f"Generated search queries: {search_queries}")
    
    # 2. Detect relevant topics
    detected_topics = detect_relevant_topics(user_message)
    print(f"Detected topics: {detected_topics}")

    # 3. Perform hybrid search
    session = get_db_session()
    if not session:
        return jsonify({'error': 'Could not get database session.'}), 500
        
    try:
        # Perform hybrid search combining vector, topic, and full-text search
        verses, paragraphs = hybrid_search(session, search_queries, detected_topics, user_message)
        
        print(f"Found {len(verses)} verses and {len(paragraphs)} paragraphs")
        
        if not verses and not paragraphs:
            return jsonify({'reply': "I couldn't find any relevant verses or talks for your question."})

        # 4. Use LLM to select the best 2 verses and 2 paragraphs
        selected_verses, selected_paragraphs = select_best_results_with_llm(
            user_message, verses, paragraphs, num_verses=2, num_paragraphs=2
        )
        
        # 5. Format the reply
        reply = format_response_with_links(user_message, selected_verses, selected_paragraphs, session)
        print(f"Reply: {reply['reply']}")

        return jsonify(reply)

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'error': 'An error occurred while querying the database.'}), 500
    finally:
        if session:
            session.close()

@app.route('/chapter/<book>/<chapter>', methods=['GET'])
def get_chapter(book: str, chapter: str):
    """
    Serves chapter content in read-only mode.
    Book and chapter are passed as URL parameters.
    """
    try:
        # Convert URL-friendly format back to proper format
        book_name = book.replace('-', ' ').title()
        chapter_num = chapter
        
        # Handle special cases for book names
        if book_name.startswith('1 ') or book_name.startswith('2 ') or book_name.startswith('3 '):
            # Handle books like "1 Nephi", "2 Corinthians", etc.
            book_name = book_name.replace('1 ', '1 ').replace('2 ', '2 ').replace('3 ', '3 ')
        
        session = get_db_session()
        if not session:
            return jsonify({'error': 'Could not get database session.'}), 500
        
        try:
            # Query for chapter content
            chapter_query = """
            MATCH (c:Chapter)<-[:CONTAINS]-(b:Book)
            WHERE b.title CONTAINS $book AND c.number = $chapter
            WITH c, b
            OPTIONAL MATCH (c)-[:CONTAINS]->(v:Verse)
            WITH c, b, collect({number: v.number, text: v.text}) AS verses
            RETURN b.title AS book_title, c.number AS chapter_number, c.summary AS summary, verses
            ORDER BY v.number
            """
            
            result = session.run(chapter_query, book=book_name, chapter=int(chapter_num))
            chapter_data = result.single()
            
            if not chapter_data:
                return jsonify({'error': f'Chapter {chapter_num} of {book_name} not found.'}), 404
            
            # Format the response
            verses = sorted(chapter_data['verses'], key=lambda x: x['number'])
            
            chapter_content = {
                'book_title': chapter_data['book_title'],
                'chapter_number': chapter_data['chapter_number'],
                'summary': chapter_data['summary'],
                'verses': verses,
                'full_reference': f"{chapter_data['book_title']} {chapter_data['chapter_number']}",
                'verse_count': len(verses)
            }
            
            return jsonify(chapter_content)
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"Error getting chapter {book} {chapter}: {e}")
        return jsonify({'error': 'An error occurred while retrieving chapter content.'}), 500

@app.route('/topic/<topic_name>', methods=['GET'])
def get_topic_content(topic_name: str):
    """
    Serves topic content with related verses and talks.
    """
    try:
        # Convert URL-friendly format back to proper format
        topic_display_name = topic_name.replace('-', ' ').title()
        
        session = get_db_session()
        if not session:
            return jsonify({'error': 'Could not get database session.'}), 500
        
        try:
            # Query for topic content
            topic_query = """
            MATCH (tp:Topic {name: $topic})
            OPTIONAL MATCH (tp)-[:MENTIONS]->(v:Verse)
            OPTIONAL MATCH (tp)-[:MENTIONS]->(t:Talk)
            WITH tp, collect(DISTINCT v) AS verses, collect(DISTINCT t) AS talks
            RETURN tp.name AS topic_name, verses, talks
            """
            
            result = session.run(topic_query, topic=topic_display_name)
            topic_data = result.single()
            
            if not topic_data:
                return jsonify({'error': f'Topic "{topic_display_name}" not found.'}), 404
            
            # Format verses with chapter info
            formatted_verses = []
            for verse in topic_data['verses'][:10]:  # Limit to 10 verses
                # Get chapter info for each verse
                chapter_query = """
                MATCH (v:Verse {id: $verse_id})<-[:CONTAINS]-(c:Chapter)<-[:CONTAINS]-(b:Book)
                RETURN b.title AS book_title, c.number AS chapter_number, v.number AS verse_number
                """
                chapter_result = session.run(chapter_query, verse_id=verse['id'])
                chapter_info = chapter_result.single()
                
                if chapter_info:
                    formatted_verses.append({
                        'text': clean_text(verse['text']),
                        'source': f"{chapter_info['book_title']} {chapter_info['chapter_number']}:{chapter_info['verse_number']}",
                        'chapter_info': {
                            'book': chapter_info['book_title'],
                            'chapter': str(chapter_info['chapter_number']),
                            'chapter_url': f"/chapter/{chapter_info['book_title'].replace(' ', '-').lower()}/{chapter_info['chapter_number']}"
                        }
                    })
            
            # Format talks
            formatted_talks = []
            for talk in topic_data['talks'][:5]:  # Limit to 5 talks
                formatted_talks.append({
                    'title': clean_text(talk['title']),
                    'year': talk.get('year', 'Unknown'),
                    'season': talk.get('season', 'Unknown')
                })
            
            topic_content = {
                'topic_name': topic_data['topic_name'],
                'verses': formatted_verses,
                'talks': formatted_talks,
                'verse_count': len(topic_data['verses']),
                'talk_count': len(topic_data['talks'])
            }
            
            return jsonify(topic_content)
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"Error getting topic {topic_name}: {e}")
        return jsonify({'error': 'An error occurred while retrieving topic content.'}), 500

@app.route('/talk/<talk_title>', methods=['GET'])
def get_talk_content(talk_title: str):
    try:
        session = get_db_session()
        if not session:
            return jsonify({'error': 'Could not get database session.'}), 500
        try:
            talk_query = """
            MATCH (t:Talk {title: $title})-[:CONTAINS]->(p:Paragraph)
            RETURN t.title AS title, t.year AS year, t.season AS season, collect(p.text) AS paragraphs
            """
            result = session.run(talk_query, title=talk_title)
            talk_data = result.single()
            if not talk_data:
                return jsonify({'error': f'Talk "{talk_title}" not found.'}), 404
            return jsonify({
                'title': talk_data['title'],
                'year': talk_data['year'],
                'season': talk_data['season'],
                'paragraphs': talk_data['paragraphs']
            })
        finally:
            session.close()
    except Exception as e:
        print(f"Error getting talk {talk_title}: {e}")
        return jsonify({'error': 'An error occurred while retrieving talk content.'}), 500

if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on local network
    app.run(host='0.0.0.0', port=5000, debug=True)
