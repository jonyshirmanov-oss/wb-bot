import os
import re
import logging
import requests
import json
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

def extract_article(url: str):
    match = re.search(r'/catalog/(\d+)', url)
    if match:
        return match.group(1)
    match = re.search(r'(\d{7,12})', url)
    if match:
        return match.group(1)
    return None

def get_basket(vol: int) -> str:
    if vol <= 143: return "01"
    elif vol <= 287: return "02"
    elif vol <= 431: return "03"
    elif vol <= 719: return "04"
    elif vol <= 1007: return "05"
    elif vol <= 1061: return "06"
    elif vol <= 1115: return "07"
    elif vol <= 1169: return "08"
    elif vol <= 1313: return "09"
    elif vol <= 1601: return "10"
    elif vol <= 1655: return "11"
    elif vol <= 1919: return "12"
    elif vol <= 2045: return "13"
    elif vol <= 2189: return "14"
    elif vol <= 2405: return "15"
    elif vol <= 2621: return "16"
    elif vol <= 2837: return "17"
    else: return "18"

def get_product_info(article: str):
    article_int = int(article)
    vol = article_int // 100000
    part = article_int // 1000
    basket = get_basket(vol)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.wildberries.ru/",
        "Origin": "https://www.wildberries.ru",
        "Connection": "keep-alive",
    })

    product = {}

    # Шаг 1: card.json для названия и бренда
    card_url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{article}/info/ru/card.json"
    try:
        r = session.get(card_url, timeout=15)
        logger.info(f"card.json [{r.status_code}]: {card_url}")
        if r.status_code == 200:
            data = r.json()
            product["name"] = data.get("imt_name") or data.get("subj_name") or ""
            product["brand"] = data.get("brand_name") or ""
            logger.info(f"card.json name={product.get('name')} brand={product.get('brand')}")
    except Exception as e:
        logger.error(f"card.json error: {e}")

    # Шаг 2: price.json для цены
    price_url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{article}/info/price-history.json"
    try:
        r = session.get(price_url, timeout=15)
        logger.info(f"price.json [{r.status_code}]")
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0:
                last = data[-1]
                price_val = last.get("price", {})
                if price_val:
                    product["price"] = price_val.get("RUB", 0) // 100
                    logger.info(f"price from history: {product.get('price')}")
    except Exception as e:
        logger.error(f"price.json error: {e}")

    # Шаг 3: API WB для цены, рейтинга, отзывов
    api_url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={article}"
    try:
        r = session.get(api_url, timeout=15)
        logger.info(f"card API [{r.status_code}]")
        if r.status_code == 200:
            data = r.json()
            products = data.get("data", {}).get("products", [])
            if products:
                p = products[0]
                if not product.get("name"):
                    product["name"] = p.get("name", "")
                if not product.get("brand"):
                    product["brand"] = p.get("brand", "")
                product["rating"] = p.get("rating", 0)
                product["feedbacks"] = p.get("feedbacks", 0)
                sizes = p.get("sizes", [])
                for size in sizes:
                    pd = size.get("price", {})
                    if pd and pd.get("product"):
                        product["price"] = pd["product"] // 100
                        product["original_price"] = pd.get("basic", 0) // 100
                        break
                logger.info(f"API: rating={product.get('rating')} price={product.get('price')}")
    except Exception as e:
        logger.error(f"card API error: {e}")

    # Шаг 4: Попробуем nmid API
    if not product.get("price"):
        try:
            nm_url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
            r2 = session.get(nm_url, timeout=15)
            logger.info(f"WB page [{r2.status_code}]")
            text = r2.text
            # Ищем цену в HTML
            price_match = re.search(r'"priceU":(\d+)', text)
            if price_match:
                product["price"] = int(price_match.group(1)) // 100
            sale_match = re.search(r'"salePriceU":(\d+)', text)
            if sale_match:
                product["original_price"] = int(sale_match.group(1)) // 100
        except Exception as e:
            logger.error(f"WB page error: {e}")

    if not product.get("name"):
        logger.error(f"No name found for article {article}")
        return None

    # Фото
    photos = []
    for i in range(1, 5):
        photo_url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{article}/images/big/{i}.jpg"
        photos.append(photo_url)

    return {
        "name": product.get("name", "Товар с Wildberries"),
        "brand": product.get("brand", ""),
        "rating": product.get("rating", 0),
        "feedbacks": product.get("feedbacks", 0),
        "price": product.get("price"),
        "original_price": product.get("original_price"),
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
        price_str = "💰 Цена на сайте"

    brand = product.get("brand", "")
    brand_str = f"🏷 <b>{brand}</b>\n" if brand else ""

    return (
        f"🛍 <b>{product['name']}</b>\n\n"
        f"{brand_str}"
        f"{price_str}\n\n"
        f"⭐ Рейтинг: {rating_str} {feedbacks_str}\n\n"
        f"🔗 <a href='{product['url']}'>Смотреть на Wildberries</a>"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Отправь ссылку на товар Wildberries — опубликую пост в группу.\n\n"
        "📌 Пример:\nhttps://www.wildberries.ru/catalog/215482022/detail.aspx"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "wildberries.ru" not in text and "wb.ru" not in text:
        await update.message.reply_text("❌ Это не ссылка Wildberries.")
        return

    msg = await update.message.reply_text("⏳ Получаю данные о товаре...")
    article = extract_article(text)

    if not article:
        await msg.edit_text("❌ Не найден артикул в ссылке.")
        return

    logger.info(f"Processing article: {article}")
    product = get_product_info(article)

    if not product:
        await msg.edit_text("❌ Не удалось получить данные. Попробуй другую ссылку.")
        return

    post_text = format_post(product)

    try:
        valid_photos = []
        for photo_url in product["photos"][:4]:
            try:
                r = requests.head(photo_url, timeout=8)
                if r.status_code == 200:
                    valid_photos.append(photo_url)
            except:
                continue

        logger.info(f"Valid photos: {len(valid_photos)}")

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
        logger.error(f"Publish error: {e}")
        await msg.edit_text(f"❌ Ошибка публикации: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
