import logging
import base64
import requests
from io import BytesIO
from PIL import Image
import telebot
import openai
import os
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)

# Retrieve the API keys from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

# Initialize the OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_KEY"))

# Initialize the bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


# Function to upload the image to ImgBB
def upload_image_to_imgbb(file_data):
    try:
        # Ensure that the image is saved in JPEG format
        image = Image.open(BytesIO(file_data))
        output = BytesIO()
        image.convert("RGB").save(output, format="JPEG")
        output.seek(0)

        # Convert the image to base64
        encoded_image = base64.b64encode(output.getvalue()).decode('utf-8')

        # Prepare the request to ImgBB
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
            "image": encoded_image
        }

        response = requests.post(url, data=payload)
        logging.info(f"ImgBB response status code: {response.status_code}")
        logging.info(f"ImgBB response text: {response.text}")

        if response.status_code == 200:
            result = response.json()
            logging.info(f"Image uploaded successfully to ImgBB: {result['data']['url']}")
            return result['data']['url']
        else:
            logging.error(f"Failed to upload image to ImgBB: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"Exception during image upload to ImgBB: {str(e)}")
        return None


# Function to analyze the image using OpenAI's Vision API with retry
def analyze_image_openai(image_url, retries=3, delay=2):
    for attempt in range(retries):
        try:
            # Log the image URL being sent
            logging.info(f"Sending image URL to OpenAI Vision API: {image_url}")

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Ensure you're using the correct GPT-4 Vision model
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What’s in this image?"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
            )

            logging.info(f"OpenAI Vision response: {response}")

            # Extract and return the text result
            return response.choices[0].message.content.strip()

        except Exception as e:
            logging.error(f"Error analyzing image with OpenAI Vision on attempt {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logging.error("Max retries reached. Failed to analyze image.")
                return None


# Handler for received photos
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        # Download the image file from Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        file_data = bot.download_file(file_info.file_path)

        # Convert WebP to JPEG if needed
        try:
            image = Image.open(BytesIO(file_data))
            if image.format == "WEBP":
                output = BytesIO()
                image.convert("RGB").save(output, format="JPEG")
                file_data = output.getvalue()  # Update the file_data with JPEG content
                logging.info("Converted WebP image to JPEG format")
        except Exception as e:
            logging.error(f"Error processing image format: {str(e)}")
            bot.reply_to(message, "Failed to process the image format.")
            return

        # Upload image to ImgBB
        image_url = upload_image_to_imgbb(file_data)
        if not image_url:
            bot.reply_to(message, "Failed to upload image to ImgBB.")
            return

        # Analyze image using OpenAI Vision API
        analysis_result = analyze_image_openai(image_url)
        if analysis_result:
            bot.reply_to(message, f"Image analysis result:\n{analysis_result}")
        else:
            bot.reply_to(message, "Failed to analyze image using OpenAI Vision API.")

    except Exception as e:
        logging.error(f"Error handling photo: {str(e)}")
        bot.reply_to(message, "Failed to process the image.")


# Handler for /start command
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Send me an image (JPG or WebP), and I’ll analyze it for you.")


# Start polling
if __name__ == "__main__":
    logging.info("Bot is running...")
    bot.polling()
