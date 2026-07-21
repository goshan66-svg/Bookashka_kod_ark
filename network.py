import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from mega import Mega

class FFMpegProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Выключаем мусорные логи в консоли."""
        pass

    def do_GET(self):
        """Ловим запрос от ffpyplayer, отдаем Content-Length и транслируем чанки."""
        try:
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            file_h = query_params.get('h', [None])[0]
            raw_k_list = query_params.get('k', [])
            
            if not file_h or not raw_k_list:
                self.send_error(400, "Missing handle or key")
                return

            # Чистим крипто-ключ от мусорных скобок URL-кодирования
            clean_numbers = []
            for item in raw_k_list:
                cleaned = item.replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace("'", "").strip()
                if ',' in cleaned:
                    for sub in cleaned.split(','):
                        if sub.strip(): clean_numbers.append(int(sub.strip()))
                else:
                    if cleaned: clean_numbers.append(int(cleaned))
            file_k = clean_numbers if len(clean_numbers) == 4 else raw_k_list

            # 1. Подключаемся к MEGA, чтобы узнать точный размер ОДНОГО этого файла
            from network import get_mega_session
            mega_client = get_mega_session()
            if not mega_client:
                mega_client = Mega().login("твой_логин", "пароль")

            # Запрашиваем параметры файла у MEGA по его ID
            file_info = mega_client._api_request({'a': 'g', 'g': 1, 'n': file_h})
            if 'g' not in file_info:
                self.send_error(404, "File not accessible")
                return
                
            file_size = file_info['s'] # Точный размер этого MP3 файла в байтах

            print(f"[Прокси] FFmpeg запросил файл. Передаем Content-Length: {file_size} байт.")

            # 2. ОТПРАВЛЯЕМ ЖЕСТКИЕ HTTP-ЗАГОЛОВКИ ДЛЯ ДВИЖКА FFmpeg
            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Length', str(file_size)) # Даем FFmpeg точный размер для шкалы времени!
            self.send_header('Accept-Ranges', 'bytes')         # Разрешаем FFmpeg делать дозапросы перемотки
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            # 3. Запускаем наш исправленный дешифратор из mega.py
            # Он будет стримить чанки этого конкретного файла напрямую в память
            for audio_chunk in mega_client.stream_audio_chunks(file_h, file_key=file_k):
                if not audio_chunk:
                    break
                # Вливаем байты напрямую в сетевой поток FFmpeg
                self.wfile.write(audio_chunk)
                
            print(f"[Прокси] Стриминг файла {file_h} успешно завершен.")

        except ConnectionError:
            # Нормальное поведение FFmpeg: прочитал заголовок, закрыл соединение и открыл новое
            print("[Прокси] FFmpeg переподключил поток.")
        except Exception as e:
            print(f"[Прокси] Ошибка трансляции: {e}")

def start_proxy_server():
    """Запускает прокси на порту 9999 для обслуживания FFmpeg плеера."""
    def run_server():
        server_address = ('127.0.0.1', 9999)
        httpd = HTTPServer(server_address, FFMpegProxyHandler)
        print("[Прокси] Запущен шлюз для FFmpeg на http://127.0.0.1:9999")
        httpd.serve_forever()

    import threading
    threading.Thread(target=run_server, daemon=True).start()
