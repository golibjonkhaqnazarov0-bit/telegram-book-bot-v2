# Telegram Bot (Kitob Platformasi)

Ushbu bot kitoblar platformasini boshqarish uchun mo'ljallangan.

## 24/7 Ishga tushirish (Deployment)

Botni 24/7 rejimida ishlashi uchun quyidagi usullardan foydalanishingiz mumkin:

### 1. Docker orqali (Tavsiya etiladi)
```bash
docker build -t telegram-bot .
docker run -d --name my-bot -e BOT_TOKEN="SIZNING_TOKENINGIZ" -e ADMIN_ID="SIZNING_IDINGIZ" telegram-bot
```

### 2. start.sh skripti orqali
```bash
chmod +x start.sh
export BOT_TOKEN="SIZNING_TOKENINGIZ"
export ADMIN_ID="SIZNING_IDINGIZ"
./start.sh
```

## Konfiguratsiya
Bot ishlashi uchun `BOT_TOKEN` va `ADMIN_ID` muhit o'zgaruvchilarini (environment variables) o'rnatishingiz kerak.
