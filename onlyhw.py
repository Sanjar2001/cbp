import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from openai import AsyncOpenAI
import openai
from openai.types.chat import ChatCompletion
import os
from dotenv import load_dotenv
import asyncio
import time
from aiogram.methods import SendChatAction
import base64

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Проверка API ключа OpenAI
if not OPENAI_API_KEY:
    logger.error("OpenAI API key is not set. Please check your .env file.")
    raise ValueError("OpenAI API key is not set")

# Инициализация OpenAI API
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Словарь для хранения контекста пользователей
user_contexts = {}

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: Message):
    """Handler for the /start command."""
    try:
        user_id = message.from_user.id
        logger.info(f"Start command from User ID ({user_id})")
        
        if user_id not in user_contexts:
            user_contexts[user_id] = {"context": [], "tokens": 1000, "last_token_reset": 0}
            logger.info(f"User ID ({user_id}) not in DB, registered new user")
        else:
            logger.info(f"User ID ({user_id}) in DB, greeting existing user")
        
        welcome_message = (
            "Ahoy, matey! I be the pirate bot. What treasure can I help ye find?\n\n"
            "Here be me commands:\n"
            "/tokens - Check or replenish yer tokens\n"
            "/clean - Clear yer chat history\n"
            "/describe_image - Send an image, and I'll tell ye what I see!"
        )
        await message.reply(welcome_message)
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")

@dp.message(Command("tokens"))
async def tokens_command(message: Message):
    """Handler for the /tokens command to replenish tokens."""
    try:
        user_id = message.from_user.id
        logger.info(f"Tokens command from User ID ({user_id})")
        
        if user_id in user_contexts:
            current_time = time.time()
            if current_time - user_contexts[user_id].get("last_token_reset", 0) >= 180:  # 3 minutes
                user_contexts[user_id]["tokens"] = 1000
                user_contexts[user_id]["last_token_reset"] = current_time
                logger.info(f"User ID ({user_id}) in DB, tokens reset")
                await message.reply("Yarr! Yer tokens be replenished to 1000, ye lucky dog!")
            else:
                remaining_time = 180 - (current_time - user_contexts[user_id]["last_token_reset"])
                await message.reply(f"Hold yer horses, matey! Ye must wait {int(remaining_time)} more seconds to reset yer tokens!")
        else:
            logger.warning(f"User ID ({user_id}) not in DB, can't reset tokens")
            await message.reply("Blimey! Ye be not registered in me crew. Use /start to join!")
    except Exception as e:
        logger.error(f"Error in tokens command: {str(e)}")

@dp.message(Command("clean"))
async def clean_command(message: Message):
    """Handler for the /clean command to clear context."""
    try:
        user_id = message.from_user.id
        logger.info(f"Clean command from User ID ({user_id})")
        
        if user_id in user_contexts:
            user_contexts[user_id]["context"] = []
            logger.info(f"User ID ({user_id}) context cleared")
            await message.reply("Shiver me timbers! Yer context be cleared like a clean deck!")
        else:
            logger.warning(f"User ID ({user_id}) not in DB, can't clear context")
            await message.reply("Blimey! Ye be not registered in me crew. Use /start to join!")
    except Exception as e:
        logger.error(f"Error in clean command: {str(e)}")

@dp.message(Command("describe_image"))
async def describe_image_command(message: Message):
    """Handler for the /describe_image command."""
    try:
        # Check if the message has a photo
        if not message.photo:
            await message.reply("Please send an image with this command.")
            return

        # Get the file ID of the largest photo
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path

        # Download the image
        image_data = await bot.download_file(file_path)

        # Read bytes from BytesIO object
        image_bytes = image_data.read()

        # Send "typing" action
        await bot(SendChatAction(chat_id=message.chat.id, action="typing"))

        # Generate image description
        description = await generate_image_description(image_bytes)
        
        await message.reply(description)
    except Exception as e:
        logger.error(f"Error in describe_image command: {str(e)}")
        await message.reply("An error occurred while processing the image. Please try again.")

async def generate_image_description(image_data: bytes) -> str:
    """Generate a description of the image using OpenAI's Vision model."""
    try:
        # Encode the image to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image? Describe it in detail."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ],
                }
            ],
            max_tokens=300,
        )

        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error in generate_image_description: {str(e)}")
        return "Arrr! I be having trouble seeing that image. Can ye try another?"

@dp.message()
async def handle_message(message: Message):
    """Handler for incoming messages."""
    try:
        user_id = message.from_user.id
        
        # Check if the message contains text
        if message.text:
            user_message = message.text
            logger.info(f"New text message from User ID ({user_id}) Message: {user_message}")

            # Send "typing" action
            await bot(SendChatAction(chat_id=message.chat.id, action="typing"))
            
            response = await generate_response(user_id, user_message)
            logger.info(f"For User ID ({user_id}) replied to message ({user_message}). Response: {response}")
            
            await message.reply(response)
        elif message.photo:
            # Handle photo messages
            await describe_image_command(message)
        else:
            # Handle other types of messages
            await message.reply("Arrr! I can only understand text and images, ye scurvy dog!")
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")

async def generate_response(user_id: int, message: str) -> str:
    """Generate a response using OpenAI API."""
    try:
        max_context_length = 10  # Maximum number of messages in context
        user_contexts[user_id]["context"].append({"role": "user", "content": message})
        
        # Trim context if it exceeds max length
        if len(user_contexts[user_id]["context"]) > max_context_length:
            user_contexts[user_id]["context"] = user_contexts[user_id]["context"][-max_context_length:]
        
        response: ChatCompletion = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ye be a pirate bot. Speak like a true buccaneer!"},
                *user_contexts[user_id]["context"]
            ]
        )

        assistant_response = response.choices[0].message.content
        user_contexts[user_id]["context"].append({"role": "assistant", "content": assistant_response})
        
        return assistant_response
    except Exception as e:
        logger.error(f"Unexpected error in generate_response: {str(e)}")
        return "Arrr! A kraken's got me tongue. Try again, ye scurvy dog!"

async def main():
    """Main function to start the bot."""
    try:
        logger.info("Bot started polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")
    finally:
        logger.warning("Bot stopped.")

if __name__ == '__main__':
    asyncio.run(main())
