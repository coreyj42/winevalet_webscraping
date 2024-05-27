from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains, ScrollOrigin
import pandas as pd
import os
import re
import time
import numpy as np
import traceback

class TooManyChecksException(Exception):
    def __init__(self, message):
        super().__init__(message)

class TooLongSinceSaveException(Exception):
    def __init__(self, message):
        super().__init__(message)

def extract_years(value):
    # Find all 4-digit year patterns in the string
    try:
        years = re.findall(r'\b\d{4}\b', value)
        return years if years else []
    except TypeError:
        return []
    
def scroll_to(element):
    ActionChains(driver)\
        .scroll_to_element(element)\
        .perform()
    
def scroll_from(element, amount):
    scroll_origin = ScrollOrigin.from_element(element)
    ActionChains(driver)\
        .scroll_from_origin(scroll_origin, 0, amount)\
        .perform()

def scrape_and_append_review_cards(driver, all_product_reviews, last_scraped_j):
    # scrape review card data
    reviews_window = driver.find_element(By.CLASS_NAME, "baseModal__window--3r5PC")
    review_cards = reviews_window.find_elements(By.CLASS_NAME, "communityReviewItem__reviewCard--1RupJ")
    print("Scraping review cards...")
    #for review_card in review_cards:
    for j in range(last_scraped_j, len(review_cards), 1):
        #n_review_cards = len(review_cards)
        #print(f"Scraping review card j={j} of {n_review_cards-1}...")
        print(f"Scraping review card i={j}...")
        review_card = review_cards[j]
        n_loops_limit = 5
        n_loops = 0
        while True:
            try:
                rating = review_card.find_element(By.CLASS_NAME, "userRating_ratingNumber__cMtKU").text
                break
            except StaleElementReferenceException:
                if n_loops < n_loops_limit:
                    # Deal with review cards not being fully loaded
                    #print(f"Review card j={j} was not fully loaded upon retrieval of review cards. Retrying...")
                    print(f"Review card i={j} was not fully loaded upon retrieval of review cards. Retrying...")
                    reviews_window = driver.find_element(By.CLASS_NAME, "baseModal__window--3r5PC")
                    review_cards = reviews_window.find_elements(By.CLASS_NAME, "communityReviewItem__reviewCard--1RupJ")
                    review_card = review_cards[j]
                    #print(f"{n_review_cards} should equal {len(review_cards)}")
                    n_loops += 1
                    time.sleep(0.5)
                    continue
                else:
                    raise TooManyChecksException(f"Tried and failed to retrieve review card j={j} too many times due to StaleElementReferenceException") 
        user_href = ""
        username = ""
        user_review_date = ""
        # check for vintage year of review
        vintage_year = ""
        try:
            # Try to find vintage year
            vintage_year = review_card.find_element(By.CLASS_NAME, "reviewedVintageYear__vintageText--3TZOW").text
        except NoSuchElementException:
            pass
        # loop through anchors to get username and date of review
        user_anchors = review_card.find_elements(By.CLASS_NAME, "anchor_anchor__m8Qi-")
        for anchor in user_anchors:
            if "userAlias_userAlias__ztmrT" in anchor.get_attribute("class"):
                username = anchor.text
                user_href = anchor.get_attribute('href')
            if "reviewDate__reviewDate--49vpM" in anchor.get_attribute("class"):
                user_review_date = anchor.text
    
        user_review = {
            "href" : user_href,
            "username" : username,
            "rating" : rating,
            "date" : user_review_date,
            "vintage_year" : vintage_year
            }
        all_product_reviews.append(user_review)
        last_scraped_j = j
    return all_product_reviews, last_scraped_j

#load dataframes
vivino_hrefs_df = pd.read_csv('../data/vivino/filtered_matching_products.csv')
dm_wine_df = pd.read_csv("../data/cleaned_wine_df.csv")

# merge dataframes
vivino_hrefs_df = vivino_hrefs_df.merge(dm_wine_df, how='left', left_on='dm_href', right_on='href')
vivino_hrefs_df = vivino_hrefs_df[["dm_brand_name", "dm_product_name", "dm_href", "vivino_product_name", "vivino_href", "vintage"]]

# Apply the extraction function to the 'vintage' column
vivino_hrefs_df['extracted_years'] = vivino_hrefs_df['vintage'].apply(extract_years)
vivino_hrefs_df

# setup seenium options
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-infobars')
options.add_argument('--disable-extensions')
options.add_argument('--disable-notifications')
options.add_argument('--window-size=1724,968')
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
options.add_argument(f'user-agent={user_agent}')

# setup driver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# lists to make into dataframe
dm_hrefs_subset = []
dm_brand_name_subsets = []
dm_product_name_subsets = []
dm_vintage_years_subset = []
vivino_hrefs_subset = []
all_reviews_subset = []

total_wines = len(vivino_hrefs_df)
#total_wines = 2 # Used for testing
starting_i = 1771
#n_waits_limit = 3
#n_rescrolls_limit = 5
timeout_duration = 10  # Set the timeout duration
limit_before_saving = 30

###############################################
############### Start Scraping #################
while starting_i < (total_wines -1):
    products_scraped = 0
    finished = False

    # handles unexpected exceptions and save progress
    try:
        for i in range(starting_i, total_wines, 1):
        
            row = vivino_hrefs_df.iloc[i]
            href = row.vivino_href
            print(f"\n\nGetting product reviews for i={i} of {total_wines-1}: {href}")
            
            # Set the page load timeout
            driver.set_page_load_timeout(timeout_duration)
            
            # load product page
            while True:
                try:
                    # Try to load the page
                    driver.get(href)
                    break
                except TimeoutException:
                    # Handle the timeout exception
                    print(f"The page took longer than {timeout_duration} seconds to load and was aborted. Trying again...")
                    continue

            # show all reviews
            #######
            all_reviws_anchor = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(@class, 'anchor_anchor__m8Qi-') and contains(@class, 'scroll')]"))
                )
            print("Found reviews anchor")
            anchor_found = True
            previous_page_text = driver.find_element
            all_reviws_anchor.click()   
            """
            time.sleep(1)
            anchor_found = False
            anchors = driver.find_elements(By.CLASS_NAME, "anchor_anchor__m8Qi-")
            for anchor in anchors:
                if "scroll" in anchor.get_attribute("class"):
                    print("Found reviews anchor")
                    all_reviws_anchor = anchor
                    anchor_found = True
                    previous_page_text = driver.find_element
                    all_reviws_anchor.click()
                    break
            if not anchor_found:
                raise NoSuchElementException('Could not find reviews anchor')
            """
            ######

            # Click show more reviews
            #time.sleep(1)
            reviews_found = False
            reviews_button_loaded = False
            n_waits = 0
            n_wait_limit = 5
            while not reviews_button_loaded:
                buttons = driver.find_elements(By.CLASS_NAME, "MuiButtonBase-root")
                for button in buttons:
                    if button.text == "Show more reviews":
                        show_more_reviews_button = button
                        print("Found show more reviews button. Clicking...")
                        reviews_button_loaded = True
                        reviews_found = True
                        button.click()
                if not reviews_button_loaded:
                    if n_waits < n_wait_limit:
                        print("Show more reviews button not loaded. Waiting and trying again...")
                        time.sleep(0.5)
                        n_waits += 1
                    else:
                        print("Wait limit for button exceeded. No Reviews Found.")
                        reviews_button_loaded = True # Set to true if there is no button to load

            all_product_reviews = []
            if reviews_found:
                # Click sort by most_recent
                time.sleep(1)
                sort_recent_anchor = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'nchor_anchor__m8Qi-') and contains(text(), 'Recent')]"))
                )
                sort_recent_anchor.click()

                # Scroll down to load all reviews
                n_waits = 0
                n_waits_limit = 3
                n_rescrolls_limit = 3
                #reviews_window = driver.find_element(By.CLASS_NAME, "baseModal__window--3r5PC")
                reviews_window = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CLASS_NAME, "baseModal__window--3r5PC"))
                            )
                review_cards = reviews_window.find_elements(By.CLASS_NAME, "communityReviewItem__reviewCard--1RupJ")
                n_review_cards = len(review_cards)
                previous_n_review_cards = n_review_cards
                all_reviews_loaded = False


                try:
                    scrape_limit = 200
                    last_scraped_j = 0
                    while not all_reviews_loaded and last_scraped_j < 200:
                        print("number of loaded review cards =", n_review_cards)
                        reviews_window = driver.find_element(By.CLASS_NAME, "baseModal__window--3r5PC")
                        review_cards = reviews_window.find_elements(By.CLASS_NAME, "communityReviewItem__reviewCard--1RupJ")
                        last_review_card = review_cards[-1]
                        print("Scrolling to last review...")
                        scroll_to(last_review_card)
                        #loop until new reviews load
                        n_waits = 0
                        n_rescrolls = 0
                        while True:
                            time.sleep(1)
                            reviews_window = driver.find_element(By.CLASS_NAME, "baseModal__window--3r5PC")
                            review_cards = reviews_window.find_elements(By.CLASS_NAME, "communityReviewItem__reviewCard--1RupJ")
                            n_review_cards = len(review_cards)
                            print(f"Comparing number of current reviews: {n_review_cards} to number of previous reviews: {previous_n_review_cards}")
                            if n_review_cards == previous_n_review_cards:
                                if n_waits < n_waits_limit:
                                    print("Review cards have not updated. Waiting...")
                                    #time.sleep(1)
                                    n_waits += 1
                                    continue
                                elif n_rescrolls < n_rescrolls_limit:
                                    time.sleep(1)
                                    last_review_card = review_cards[-1]
                                    # scroll up and down to try refreshing page
                                    print("Attempting to rescroll page to load more reviews...")
                                    scroll_from(last_review_card, -500)
                                    time.sleep(0.5)
                                    scroll_to(last_review_card)
                                    time.sleep(0.2)
                                    scroll_from(last_review_card, 100)
                                    n_rescrolls += 1
                                    n_waits = 0
                                    continue
                                else:
                                    print("No more review cards to load. Stopping scrolling...")
                                    all_reviews_loaded = True
                                    if i == (total_wines-1):
                                        finished = True
                                        print("\n#############!!!ALL PRODUCTS COMPLETE!!!#############\n")
                                    break
                            else:
                                previous_n_review_cards = n_review_cards
                                n_rescrolls = 0
                                # Scrape review cards
                                time.sleep(1)
                                all_product_reviews, last_scraped_j = scrape_and_append_review_cards(driver, all_product_reviews, last_scraped_j+1)
                                if last_scraped_j > scrape_limit:
                                    print(f"Number of scraped reviews has exceeded limit of {scrape_limit} for this product. Saving and continuing to next product...")
                                break
                        time.sleep(2)
                except TimeoutException:
                    print("\n#############!!!TimeOutException BEFORE GETTING ALL REVIEWS!!!#############")
                    print(f"Scraped {last_scraped_j} review cards before timeout. Saving and moving to next product\n")

            # append to data lists
            dm_hrefs_subset.append(row.dm_href)
            dm_vintage_years_subset.append(row.extracted_years)
            dm_brand_name_subsets.append(row.dm_brand_name)
            dm_product_name_subsets.append(row.dm_product_name)
            vivino_hrefs_subset.append(row.vivino_href)
            all_reviews_subset.append(all_product_reviews)
            #break # break after first loop while developing

            products_scraped += 1

            # Save progress after increments
            if products_scraped >= limit_before_saving:
                i += 1 # used to start next loop at next i and correctly label saved file

                raise TooLongSinceSaveException(f"!!!Scraped {limit_before_saving} products without saving.")
    
    except Exception as e:
        print(e)
        print(f"Stopped scraping at i ={i} of {total_wines-1}: {href}")
    
    finally:

        #save results
        vivino_reviews_df = {
            "dm_href" : dm_hrefs_subset,
            "dm_vintage_years": dm_vintage_years_subset,
            "dm_brand_name": dm_brand_name_subsets,
            "dm_product_name": dm_product_name_subsets,
            "vivino_href" : vivino_hrefs_subset,
            "all_reviews" : all_reviews_subset,
        }
        vivino_reviews_df = pd.DataFrame(vivino_reviews_df)
        
    
        # save df to csv
        if finished:
            file_path = f"../data/vivino/user_resviews_subsets/vivino_user_reviews_dataset_i_{starting_i}-{i}.csv"
        else:
            file_path = f"../data/vivino/user_resviews_subsets/vivino_user_reviews_dataset_i_{starting_i}-{i-1}.csv"
        print(f"Saving results to {file_path}...")
        vivino_reviews_df.to_csv(file_path, index=False)
    
        starting_i = i

        # clear lists for dataframe
        dm_hrefs_subset = []
        dm_brand_name_subsets = []
        dm_product_name_subsets = []
        dm_vintage_years_subset = []
        vivino_hrefs_subset = []
        all_reviews_subset = []

        time.sleep(2)
    
# Close the webpage
driver.quit()