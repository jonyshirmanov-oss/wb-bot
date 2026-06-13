import os
import re
import logging
import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

def extract_article(url: str):
    patterns = [
        r"wildberries\.ru/catalog/(\d+)",
        r"wb\.ru/catalog/(\d+)",
        r"/(\d{7,12})/",
        r"nm=(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    # попробуем найти любое длинное число
    match = re.search(r"(\d{7,12})", url)
    if match:
        return match.group(1)
    return None

def get_basket(article_int):
    vol = article_int // 100000
    if vol <= 143:
        return "01"
    elif vol <= 287:
        return "02"
    elif vol <= 431:
        return "03"
    elif vol <= 719:
        return "04"
    elif vol <= 1007:
        return "05"
    elif vol <= 1061:
        return "06"
    elif vol <= 1115:
        return "07"
    elif vol <= 1169:
        return "08"
    elif vol <= 1313:
        return "09"
    elif vol <= 1601:
        return "10"
    elif vol <= 1655:
        return "11"
    elif vol <= 1919:
        return "12"
    elif vol <= 2045:
        return "13"
    elif vol <= 2189:
        return "14"
    elif vol <= 2405:
        return "15"
    elif vol <= 2621:
        return "16"
    elif vol <= 2837:
        return "17"
    else:
        return "18"

def get_product_info(article: str):
    article_int = int(article)
    
    # Пробуем разные API endpoints
    urls = [
        f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={article}",
        f"https://card.wb.ru/cards/detail?nm={article}&curr=rub&dest=-1257786&regions=80,38,4,64,83,33,68,70,69,30,86,75,40,1,66,48,110,31,22,71,114&spp=0",
    ]
    
    product = None
    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            logger.info(f"API response status: {response.status_code} for {url}")
            data = response.json()
            products = data.get("data", {}).get("products", [])
            if products:
                product = products[0]
                break
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            continue

    if not product:
        return None

    name = product.get("name", "Без названия")
    brand = product.get("brand", "")
    rating = product.get("rating", 0)
    feedbacks = product.get("feedbacks", 0)

    # Цена
    price = None
    original_price = None
    
    # Новый формат цены
    extended = product.get("extended", {})
    if extended:
        price = extended.get("clientSale", {})
        
    sizes = product.get("sizes", [])
    for size in sizes:
        price_data = size.get("price", {})
        if price_data:
            p = price_data.get("product", 0)
            b = price_data.get("basic", 0)
            if p:
                price = p // 100
                original_price = b // 100 if b else None
                break

    # Фото
    basket = get_basket(article_int)
    vol = article_int // 100000
    part = article_int // 1000
    
    photos = []
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

def format_post(product: dict) -> str:
    rating = product.get("rating", 0)
    feedbacks = product.get("feedbacks", 0)
    
    if rating:
        stars = "⭐" * min(round(rating), 5)
        rating_str = f"{rating} {stars}"
    else:
        rating_str = "нет оценок"
    
    feedbacks_str = f"({feedbacks:,} отзывов)".replace(",", " ") if feedbacks else ""

    price = product.get("price")
    original_price = product.get("original_price")
    
    if price and original_price and original_price > price:
        discount = round((1 - price / original_price) * 100)
        price_str = f"💰 <s>{original_price:,} ₽</s> → <b>{price:,} ₽</b>  🔥 -{discount}%".replace(",", " ")
    elif price:
        price_str = f"💰 <b>{price:,} ₽</b>".replace(",", " ")
    else:
        price_str = "💰 Цена уточняется"

    brand = product.get("brand", "")
    brand_str = f"🏷 <b>{brand}</b>\n" if brand else ""

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
        "📌 Пример:\nhttps://www.wildberries.ru/catalog/123456789/detail.aspx"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "wildberries.ru" not in text and "wb.ru" not in text:
        await update.message.reply_text("❌ Это не ссылка Wildberries. Попробуй ещё раз.")
        return

    msg = await update.message.reply_text("⏳ Получаю данные о товаре...")

    article = extract_article(text)
    if not article:
        await msg.edit_text("❌ Не удалось найти артикул в ссылке.")
        return

    logger.info(f"Артикул: {article}")
    product = get_product_info(article)
    
    if not product:
        await msg.edit_text("❌ Не удалось получить данные. Попробуй другую ссылку.")
        return

    post_text = format_post(product)

    try:
        valid_photos = []
        for photo_url in product["photos"][:4]:
            try:
                r = requests.head(photo_url, timeout=5, headers=HEADERS)
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

        await msg.edit_text("✅ Пост опубликован в группу!")

    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await msg.edit_text(f"❌ Ошибка при публикации: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
