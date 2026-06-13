import os
import re
import logging
import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")  # например: -1001234567890

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def extract_article(url: str) -> str | None:
    """Извлекает артикул товара из ссылки WB"""
    patterns = [
        r"wildberries\.ru/catalog/(\d+)",
        r"wb\.ru/catalog/(\d+)",
        r"/(\d{7,12})/"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_product_info(article: str) -> dict | None:
    """Получает данные о товаре через API Wildberries"""
    # Определяем корзину (basket) по артикулу
    article_int = int(article)
    if article_int <= 143:
        basket = "01"
    elif article_int <= 287:
        basket = "02"
    elif article_int <= 431:
        basket = "03"
    elif article_int <= 719:
        basket = "04"
    elif article_int <= 1007:
        basket = "05"
    elif article_int <= 1061:
        basket = "06"
    elif article_int <= 1115:
        basket = "07"
    elif article_int <= 1169:
        basket = "08"
    elif article_int <= 1313:
        basket = "09"
    elif article_int <= 1601:
        basket = "10"
    elif article_int <= 1655:
        basket = "11"
    elif article_int <= 1919:
        basket = "12"
    elif article_int <= 2045:
        basket = "13"
    elif article_int <= 2189:
        basket = "14"
    elif article_int <= 2405:
        basket = "15"
    elif article_int <= 2621:
        basket = "16"
    elif article_int <= 2837:
        basket = "17"
    else:
        basket = "18"

    # Получаем данные о товаре
    try:
        vol = article_int // 100000
        part = article_int // 1000
        api_url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={article}"
        response = requests.get(api_url, headers=HEADERS, timeout=10)
        data = response.json()

        products = data.get("data", {}).get("products", [])
        if not products:
            return None

        product = products[0]
        name = product.get("name", "Без названия")
        brand = product.get("brand", "")
        rating = product.get("rating", 0)
        feedbacks = product.get("feedbacks", 0)

        # Цена
        sizes = product.get("sizes", [])
        price = None
        original_price = None
        for size in sizes:
            price_data = size.get("price", {})
            if price_data:
                price = price_data.get("product", 0) // 100
                original_price = price_data.get("basic", 0) // 100
                break

        # Фото
        photos = []
        imt_id = product.get("root", article)
        for i in range(1, 5):
            photo_url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{article}/images/big/{i}.jpg"
            photos.append(photo_url)

        return {
            "name": name,
            "brand": brand,
            "rating": rating,
            "feedbacks": feedbacks,
            "price": price,
            "original_price": original_price,
            "photos": photos,
            "article": article,
            "url": f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        }
    except Exception as e:
        logger.error(f"Ошибка получения товара: {e}")
        return None

def format_post(product: dict) -> str:
    """Формирует красивый пост"""
    stars = "⭐" * round(product["rating"])
    rating_str = f"{product['rating']} {stars}" if product["rating"] else "нет оценок"
    feedbacks_str = f"({product['feedbacks']:,} отзывов)".replace(",", " ") if product["feedbacks"] else ""

    price_str = ""
    if product["price"] and product["original_price"] and product["original_price"] > product["price"]:
        discount = round((1 - product["price"] / product["original_price"]) * 100)
        price_str = f"💰 <s>{product['original_price']:,} ₽</s> → <b>{product['price']:,} ₽</b>  🔥 -{discount}%".replace(",", " ")
    elif product["price"]:
        price_str = f"💰 <b>{product['price']:,} ₽</b>".replace(",", " ")

    brand_str = f"🏷 <b>{product['brand']}</b>\n" if product["brand"] else ""

    post = (
        f"🛍 <b>{product['name']}</b>\n\n"
        f"{brand_str}"
        f"{price_str}\n\n"
        f"⭐ Рейтинг: {rating_str} {feedbacks_str}\n\n"
        f"🔗 <a href='{product['url']}'>Смотреть на Wildberries</a>"
    )
    return post

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Отправь мне ссылку на товар с Wildberries, "
        "и я опубликую красивый пост в группу.\n\n"
        "📌 Пример ссылки:\nhttps://www.wildberries.ru/catalog/123456789/detail.aspx"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "wildberries.ru" not in text and "wb.ru" not in text:
        await update.message.reply_text("❌ Это не похоже на ссылку Wildberries. Попробуй ещё раз.")
        return

    await update.message.reply_text("⏳ Получаю данные о товаре...")

    article = extract_article(text)
    if not article:
        await update.message.reply_text("❌ Не удалось найти артикул в ссылке. Проверь ссылку.")
        return

    product = get_product_info(article)
    if not product:
        await update.message.reply_text("❌ Не удалось получить данные о товаре. Проверь ссылку или попробуй позже.")
        return

    post_text = format_post(product)

    # Пробуем отправить с фото
    try:
        valid_photos = []
        for photo_url in product["photos"][:4]:
            try:
                r = requests.head(photo_url, timeout=5)
                if r.status_code == 200:
                    valid_photos.append(photo_url)
            except:
                continue

        if valid_photos:
            media_group = []
            for i, photo_url in enumerate(valid_photos):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_url, caption=post_text, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo_url))

            await context.bot.send_media_group(chat_id=GROUP_ID, media=media_group)
        else:
            await context.bot.send_message(chat_id=GROUP_ID, text=post_text, parse_mode="HTML")

        await update.message.reply_text("✅ Пост успешно опубликован в группу!")

    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await update.message.reply_text(f"❌ Ошибка при публикации: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
