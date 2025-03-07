import requests
from datetime import datetime, timedelta
import openai
import time
import os
from typing import List, Dict
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Configuration from environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

NEWSAPI_AI_KEY = os.getenv('NEWSAPI_AI_KEY')
if not NEWSAPI_AI_KEY:
    raise ValueError("NEWSAPI_AI_KEY environment variable is not set")

def compare_with_benchmark(benchmark_article: Dict, article: Dict) -> bool:
    """Compare an article with the benchmark article using OpenAI."""
    try:
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Prepare the prompt
        prompt = f"""
        Compare these two news articles about Elon Musk:

        BENCHMARK ARTICLE:
        Title: {benchmark_article['title']}
        Description: {benchmark_article['description']}
        Published: {benchmark_article['publishedAt']}

        ARTICLE TO COMPARE:
        Title: {article['title']}
        Description: {article['description']}
        Published: {article['publishedAt']}

        First, identify the SPECIFIC EVENT in each article:
        1. What exactly happened?
        2. When did it happen?
        3. Who was involved?

        Then classify their relationship as ONE of these categories:

        - 'identical': The articles must cover the EXACT SAME specific incident or event
          Example: Both articles reporting on "DOGE using U.S. Marshals to take over an agency on Thursday"
          Counter-example: Articles about different aspects of DOGE's activities, even if from the same day
        
        - 'supporting': Articles about different but related events that support or align with the benchmark's narrative
          Example: If benchmark is about DOGE taking over an agency, a supporting article might be about legal justification for the takeover
        
        - 'contradicting': Articles about the same specific event but presenting opposing views or criticisms
          Example: One article supporting the agency takeover, another condemning it as illegal
        
        - 'unrelated': Articles about different events or topics, even if they involve the same organization (DOGE)
          Example: If benchmark is about agency takeover, articles about DOGE's general authority or other activities are unrelated

        Key rules:
        1. For 'identical', the articles must describe the EXACT SAME incident, not just related developments
        2. Time proximity alone doesn't make articles identical - the specific event must match
        3. Different developments in the same story should be 'supporting' or 'unrelated', not 'identical'
        4. 'contradicting' requires opposing views about the SAME specific event
        
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
    print(f"Description: {article['description']}")

def fetch_elon_news():
    # API configuration
    base_url = 'https://eventregistry.org/api/v1/article/getArticles'
    
    # Calculate date for last 7 days of news
    today = datetime.now()
    week_ago = today - timedelta(days=2)
    
    # Parameters for the API request
    params = {
        "action": "getArticles",
        "keyword": "Elon Musk",
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
        elon_articles = []
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
            
            # Filter and add articles with "Elon" in title
            page_elon_articles = [
                {
                    'title': article['title'],
                    'description': article.get('body', article.get('description', '')),
                    'source': {'name': article.get('source', {}).get('title', 'Unknown')},
                    'publishedAt': article['dateTime'],
                    'url': article['url']
                }
                for article in news_data['articles']['results']
                if 'elon' in article['title'].lower()
            ]
            
            # Debug: Print date range of articles found
            if page_elon_articles:
                oldest = min(page_elon_articles, key=lambda x: x['publishedAt'])
                newest = max(page_elon_articles, key=lambda x: x['publishedAt'])
                print(f"\nPage {page} article dates range:")
                print(f"Oldest: {oldest['publishedAt']}")
                print(f"Newest: {newest['publishedAt']}")
            
            elon_articles.extend(page_elon_articles)
            
            # Print progress
            print(f"\rFetched page {page}, found {len(page_elon_articles)} relevant articles on this page...")
            
            # Check if we've got all articles or reached the end
            if len(news_data['articles']['results']) < params['articlesCount']:
                break
                
            page += 1
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.1)

            if page > 5:  # Limit to 5 pages for now
                print("\nReached maximum page limit")
                break
        
        print(f"\nTotal articles with 'Elon' in title: {len(elon_articles)}")
            
        if not elon_articles:
            print("No articles with 'Elon' in the title found.")
            return

        # Get the benchmark (last) article
        benchmark_article = elon_articles[-1]
        print("\n=== Benchmark Article ===")
        print_article(benchmark_article)
        print("\n=== Analyzing Related Articles ===")

        # Compare other articles with the benchmark
        relations = defaultdict(list)
        total_articles = len(elon_articles) - 1
        for i, article in enumerate(elon_articles[:-1], 1):  # Exclude the benchmark article
            print(f"\rProcessing article {i}/{total_articles}...", end="")
            relation = compare_with_benchmark(benchmark_article, article)
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
    fetch_elon_news() 