import requests
from datetime import datetime, timedelta
import openai
import time
import os
from typing import List, Dict
from collections import defaultdict
from dotenv import load_dotenv
import sys

# Load environment variables from .env file
load_dotenv()

# Set up logging to both file and console
class TeeLogger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log_file = open(filename, 'w', encoding='utf-8')  # 'w' mode overwrites the file

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()  # Ensure immediate writing to file

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Set up the logger with current timestamp
current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
log_filename = f'logs/news_analysis_{current_time}.log'
sys.stdout = TeeLogger(log_filename)

# API Configuration from environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

NEWSAPI_AI_KEY = os.getenv('NEWSAPI_AI_KEY')
if not NEWSAPI_AI_KEY:
    raise ValueError("NEWSAPI_AI_KEY environment variable is not set")

def compare_with_benchmark(keyword: str,benchmark_article: Dict, article: Dict) -> bool:
    """Compare an article with the benchmark article using OpenAI."""
    try:
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Prepare the prompt
        prompt = f"""
        Compare these two news articles about {keyword}:

        BENCHMARK ARTICLE:
        Title: {benchmark_article['title']}
        Description: {benchmark_article['description']}
        Published: {benchmark_article['publishedAt']}

        ARTICLE TO COMPARE:
        Title: {article['title']}
        Description: {article['description']}
        Published: {article['publishedAt']}

        First, identify the SPECIFIC MAIN TOPIC in each article:
        1. What exactly is the primary subject matter?
        2. What specific event or development is being reported?
        3. Who was involved and how?

        Then classify their relationship as ONE of these categories:

        - 'identical': The articles must cover the EXACT SAME specific incident or event
          Example: Both articles reporting on "{keyword}'s wealth decreasing by X billion dollars due to Tesla stock decline"
          Counter-example: One about Tesla stock decline and another about SpaceX successes, even if both mention wealth
        
        - 'supporting': Articles about different but directly related developments that support or align with the benchmark's SPECIFIC TOPIC
          Example: If benchmark is about "Tesla stock decline impacting Musk's wealth", a supporting article might be about "reasons for Tesla's stock decline" or "analysis of Musk's changing wealth"
        
        - 'contradicting': Articles that directly oppose or contradict the benchmark's specific claims about the same topic
          Example: If benchmark says "Musk's wealth decreased", a contradicting article might claim "Musk's wealth actually increased"
        
        - 'unrelated': Articles about different events or topics involving {keyword} but not directly related to the benchmark's SPECIFIC TOPIC
          Example: If benchmark is about "Musk's wealth and Tesla stock", articles about "Musk's social media posts", "political activities", or "SpaceX" are unrelated

        Key rules:
        1. Focus on the SPECIFIC TOPIC of each article, not just that they both involve {keyword}
        2. 'supporting' requires direct topical relationship to the benchmark's main subject (not just about {keyword})
        3. Time proximity alone doesn't make articles related - the specific topic must be connected
        4. Different developments in the same broader story are only 'supporting' if they directly relate to the benchmark's main topic
        5. When in doubt between 'supporting' and 'unrelated', favor 'unrelated' unless there's a clear topical connection
        
        Reply with ONLY ONE word: identical, supporting, contradicting, or unrelated.
        """

        # Make API call
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {"role": "system", "content": "You are a news analysis assistant focused on identifying relationships between articles. Respond with exactly one word from the allowed options."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        return response.choices[0].message.content.strip().lower()

    except Exception as e:
        print(f"Error in OpenAI comparison: {e}")
        return "error"

def print_article(article: Dict, index: int = None):
    """Helper function to print article details"""
    prefix = f"Article {index}:" if index is not None else "Article:"
    print(f"\n{prefix}")
    print(f"Title: {article['title']}")
    print(f"Source: {article['source']['name']}")
    print(f"Published: {article['publishedAt']}")
    print(f"URL: {article['url']}")
    print(f"Description: {article['description'][:200]}...")

def fetch_keyword_news():
    # API configuration
    base_url = 'https://eventregistry.org/api/v1/article/getArticles'
    
    # Calculate date for last 7 days of news
    today = datetime.now()
    week_ago = today - timedelta(days=30)
    
    keyword = "Eric Schmidt"
    filter_words = ["Eric", "Schmidt"]

    # Parameters for the API request
    params = {
        "action": "getArticles",
        "keyword": keyword,
        "articlesPage": 1,
        "articlesCount": 100,
        "articlesSortBy": "date",
        "articlesSortByAsc": False,
        "dataType": ["news"],
        "resultType": "articles",
        "apiKey": NEWSAPI_AI_KEY,
        "dateStart": week_ago.strftime('%Y-%m-%d'),
        "dateEnd": today.strftime('%Y-%m-%d'),
        "lang": ["eng"],  # English language articles
        "sourceLocationUri": "http://en.wikipedia.org/wiki/United_States"  # US sources only
    }

    # Debug: Print query details
    print(f"\nQuerying news from {params['dateStart']} to {params['dateEnd']}")

    try:
        articles = []
        topic_articles = []
        page = 1
        
        while True:
            params['articlesPage'] = page  # Updated to match API parameter name
            
            # Make the request
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            
            # Parse the JSON response
            news_data = response.json()
            
            if 'articles' not in news_data:
                print(f"Error in API response on page {page}: {news_data.get('message', 'No error message')}")
                break
            
            page_articles = [
                {
                    'title': article['title'],
                    'description': article.get('body', article.get('description', '')),
                    'source': {'name': article.get('source', {}).get('title', 'Unknown')},
                    'publishedAt': article['dateTime'],
                    'url': article['url']
                }
                for article in news_data['articles']['results']
            ]
            articles.extend(page_articles)

            # Filter and add articles with keyword (e.g. "Elon") in title
            page_topic_articles = [
                page_article
                for page_article in page_articles
                if all([filter_word.lower() in page_article['title'].lower() for filter_word in filter_words])
            ]
            topic_articles.extend(page_topic_articles)

            # Debug: Print date range of articles found
            if page_topic_articles:
                oldest = min(page_topic_articles, key=lambda x: x['publishedAt'])
                newest = max(page_topic_articles, key=lambda x: x['publishedAt'])
                print(f"\nPage {page} article dates range:")
                print(f"Oldest: {oldest['publishedAt']}")
                print(f"Newest: {newest['publishedAt']}")
                        
            # Print progress
            print(f"\rFetched page {page}, found {len(page_topic_articles)} relevant articles on this page...")
            
            # Check if we've got all articles or reached the end
            if len(news_data['articles']['results']) < params['articlesCount']:
                print(f"\nFetched all the article with {len(topic_articles)}")
                break
                
            page += 1

            if len(topic_articles) > 80: # limit to n articles for now
                print(f"\nReached maximum article limit with {len(topic_articles)}")
                break
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.1)

        print(f"\nTotal articles with '{filter_words}' in title: {len(topic_articles)}")
            
        if not topic_articles:
            print(f"No articles with '{filter_words}' in the title found.")
            return

        # Get the benchmark (last) article
        benchmark_article = topic_articles[-1]
        print("\n=== Benchmark Article ===")
        print_article(benchmark_article)
        print("\n=== Analyzing Related Articles ===")

        # Compare other articles with the benchmark
        relations = defaultdict(list)
        total_articles = len(topic_articles) - 1
        for i, article in enumerate(topic_articles[:-1], 1):  # Exclude the benchmark article
            print(f"\rProcessing article {i}/{total_articles}...", end="")
            relation = compare_with_benchmark(keyword, benchmark_article, article)
            relations[relation].append(article)
        print("\n")  # New line after progress indicator

        # Print statistics summary
        print("\n=== CATEGORY STATISTICS ===")
        total_analyzed = sum(len(relations[r]) for r in relations.keys())
        print(f"Total articles analyzed: {total_analyzed}")
        for relation in relations.keys():
            count = len(relations[relation])
            percentage = (count / total_analyzed * 100) if total_analyzed > 0 else 0
            print(f"{relation.upper()}: {count} articles ({percentage:.1f}%)")
        print("=" * 30 + "\n")

        # Print detailed articles by category, excluding unrelated
        for relation in relations.keys():
            if relations[relation] and relation != 'unrelated':
                print(f"\n=== {relation.upper()} ARTICLES ({len(relations[relation])}) ===")
                for i, article in enumerate(relations[relation], 1):
                    print_article(article, i)
                    print("-" * 80)  # Separator line
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news: {e}")

if __name__ == "__main__":
    fetch_keyword_news() 