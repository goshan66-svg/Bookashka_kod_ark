import sys
import traceback
import os

# Принудительно заставляем Kivy использовать плеер с поддержкой сетевых HTTP-потоков
os.environ["KIVY_AUDIO"] = "ffpyplayer"

# Перехват критических ошибок в файл error_log.txt
def show_exception_and_exit(exc_type, exc_value, exc_traceback):
    with open("error_log.txt", "w", encoding="utf-8") as f:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = show_exception_and_exit

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivymd.app import MDApp
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList, OneLineListItem
from kivymd.uix.progressbar import MDProgressBar
from network import fetch_catalog


class CatalogScreen(Screen):
    """Экран 1: Главный список Авторов и Книг."""
    def on_enter(self):
        self.ids.list_container.clear_widgets()
        catalog_data = fetch_catalog().get("Каталог", {})

        if not catalog_data:
            item = OneLineListItem(text="Каталог пуст или недоступен")
            self.ids.list_container.add_widget(item)
            return

        for author, items in catalog_data.items():
            if not isinstance(items, dict):
                continue
            for key, value in items.items():
                if not isinstance(value, dict):
                    continue

                if "folder_id" in value:
                    book_title = key
                    item_text = f"👤 {author} — 📖 {book_title}"
                    display_text = item_text if len(item_text) <= 26 else item_text[:23] + "..."
                    
                    item = OneLineListItem(text=display_text)
                    item.author_name = author
                    item.book_title = book_title
                    item.book_data = value
                    item.bind(on_release=self.on_item_click)
                    self.ids.list_container.add_widget(item)
                else:
                    for book_title, book_value in value.items():
                        if not isinstance(book_value, dict):
                            continue
                        item_text = f"👤 {author} — 📚 [{key}] {book_title}"
                        display_text = item_text if len(item_text) <= 26 else item_text[:23] + "..."
                        
                        item = OneLineListItem(text=display_text)
                        item.author_name = author
                        item.book_title = book_title
                        item.book_data = book_value
                        item.bind(on_release=self.on_item_click)
                        self.ids.list_container.add_widget(item)

    def on_item_click(self, instance):
        book_screen = self.manager.get_screen("book_screen")
        book_screen.load_book(instance.author_name, instance.book_title, instance.book_data)
        self.manager.current = "book_screen"


class BookScreen(Screen):
    """Экран 2: Список файлов (глав) внутри книги."""
    def load_book(self, author, book_title, book_data):
        import os
        self.ids.book_info.text = f"{author} — {book_title}"
        self.current_folder_id = book_data.get("folder_id")
        self.ids.files_container.clear_widgets()

        # 1. ЗАГРУЗКА ОПИСАНИЯ
        desc_text = "Описание на модерации..."
        if os.path.exists("pattern2.txt"):
            try:
                with open("pattern2.txt", "r", encoding="utf-8") as f:
                    desc_text = f.read()
            except Exception as e:
                print(f"[Файл] Ошибка чтения локального описания: {e}")
        self.ids.book_desc.text = desc_text

        # 2. ЗАГРУЗКА ОБЛОЖКИ
        cover_source = ""
        if os.path.exists("pattern1.jpg"):
            cover_source = "pattern1.jpg"
        self.ids.book_cover.source = cover_source

        # Поиск файлов книги
        files_data = book_data.get("files", book_data)
        if isinstance(files_data, dict):
            files = [k for k in files_data.keys() if k != "folder_id"]
        elif isinstance(files_data, list):
            files = files_data
        else:
            files = []

        if not files:
            item = OneLineListItem(text="Файлы не найдены")
            self.ids.files_container.add_widget(item)
            return

        for file_name in sorted(files):
            if not str(file_name).lower().endswith('.mp3'):
                continue
                
            item_text = f"🎵 {file_name}"
            display_text = item_text if len(item_text) <= 26 else item_text[:23] + "..."
            
            item = OneLineListItem(text=display_text)
            item.bind(on_release=lambda x, f=file_name: self.play_file(f))
            self.ids.files_container.add_widget(item)

    def play_file(self, file_name):
        import os
        import time
        from network import get_mega_session, start_chunked_download
        mega = get_mega_session()
        
        if not mega:
            print("[Ошибка] Нет активной сессии Mega.")
            return

        print(f"[Mega] Запрос ссылки для файла: {file_name} в папке {self.current_folder_id}")
        
        try:
            # 1. Забираем ВСЕ файлы из вашей учетной записи Mega
            all_files = mega.get_files()
            file_node = None
            
            # 2. Ищем нужный файл, проверяя имя и родительскую папку
            for node_id, node_data in all_files.items():
                if node_data.get('p') == self.current_folder_id:
                    if node_data.get('a', {}).get('n') == file_name:
                        file_node = (node_id, node_data)
                        break
            
            if file_node:
                # 3. Генерируем потоковую ссылку
                stream_url = mega.get_url(file_node)
                print(f"[Mega] Потоковая ссылка получена. Передаем в фоновый поток.")
                
                # Удаляем старый файл, если остался
                if os.path.exists(file_name):
                    try:
                        os.remove(file_name)
                    except Exception:
                        pass

                # 4. Запускаем конвейер скачивания кусками
                local_path = start_chunked_download(stream_url, file_name)
                
                # Обновляем мини-плеер внизу
                app = MDApp.get_running_app()
                app.update_mini_player(file_name)
                
                # 5. Включаем триггер ожидания куска
                from kivy.clock import Clock
                self.download_start_time = time.time()
                Clock.schedule_interval(lambda dt: self.check_file_ready(local_path), 0.5)
            else:
                print(f"[Mega] Файл {file_name} не найден в облаке.")
                
        except Exception as e:
            print(f"[Mega] Ошибка при получении ссылки: {e}")

    def check_file_ready(self, local_path):
        import os
        import time
        from kivy.clock import Clock
        from kivy.core.audio import SoundLoader
        app = MDApp.get_running_app()
        
        if time.time() - self.download_start_time > 15.0:
            print("[Плеер] Ошибка: Время ожидания сети истекло.")
            app.track_label.text = "Ошибка: слабый интернет"
            app.btn_play_pause.icon = "alert-circle"
            return False
            
        if os.path.exists(local_path):
            file_size = os.path.getsize(local_path)
            if file_size >= 307200 or file_size > 0:
                print(f"[Плеер] Первый кусок на месте ({file_size} байт). Включаем звук!")
                
                if hasattr(app, 'current_sound') and app.current_sound:
                    app.current_sound.stop()
                    
                app.current_sound = SoundLoader.load(local_path)
                if app.current_sound:
                    app.current_sound.play()
                else:
                    print("[Плеер] Ошибка: SoundLoader не смог прочитать файл.")
                return False
                
        return True


class GuestPlayerApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Orange"
        
        from network import get_mega_session
        mega_session = get_mega_session()
        if mega_session:
            print("[Успех] Сессия Mega активна и готова к работе.")
            # Запускаем наш локальный прокси-шлюз для стриминга аудио
            from network import start_proxy_server
            start_proxy_server()
        
        main_layout = BoxLayout(orientation="vertical")
        sm = ScreenManager()

        # --- ЭКРАН КАТАЛОГА ---
        scr1 = CatalogScreen(name="catalog_screen")
        box1 = BoxLayout(orientation="vertical", padding=10, spacing=10)
        box1.add_widget(MDLabel(text="Библиотека Авторов", halign="center", size_hint_y=None, height=50, font_style="H5"))
        
        scroll1 = ScrollView()
        list1 = MDList()
        scroll1.add_widget(list1)
        box1.add_widget(scroll1)
        scr1.add_widget(box1)
        scr1.ids.list_container = list1

        # --- ЭКРАН КНИГИ ---
        scr2 = BookScreen(name="book_screen")
        box2 = BoxLayout(orientation="vertical", padding=10, spacing=5)

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=45)
        btn_back = MDIconButton(icon="arrow-left", on_release=lambda x: setattr(sm, "current", "catalog_screen"))
        book_info = MDLabel(text="", halign="left", font_style="Subtitle1")
        header.add_widget(btn_back)
        header.add_widget(book_info)
        box2.add_widget(header)

        # ВЕРХНЯЯ ЧАСТЬ (1/3 экрана) для Обложки и Описания
        upper_layout = BoxLayout(orientation="horizontal", size_hint_y=0.33, spacing=10, padding=5)
        
        book_cover = Image(source="pattern1.jpg", size_hint_x=0.35, keep_ratio=True, allow_stretch=True)
        book_description = MDLabel(text="Описание книги загружается...", halign="left", valign="top")
        book_description.bind(size=book_description.setter('text_size'))
        
        upper_layout.add_widget(book_cover)
        upper_layout.add_widget(book_description)
        box2.add_widget(upper_layout)

        # НИЖНЯЯ ЧАСТЬ (2/3 экрана) для списка MP3 файлов
        scroll2 = ScrollView(size_hint_y=0.67)
        list2 = MDList()
        scroll2.add_widget(list2)
        box2.add_widget(scroll2)
        
        scr2.add_widget(box2)
        scr2.ids.book_info = book_info
        scr2.ids.book_cover = book_cover          
        scr2.ids.book_desc = book_description    
        scr2.ids.files_container = list2

        # Добавляем экраны в менеджер
        sm.add_widget(scr1)
        sm.add_widget(scr2)
        
        # Добавляем менеджер экранов в верхнюю часть главного контейнера
        main_layout.add_widget(sm)
        
        # --- МИНИ-ПЛЕЕР ВНИЗУ (ЗАКРЕПЛЕН ВСЕГДА) ---
        self.mini_player = BoxLayout(orientation="vertical", size_hint_y=None, height=65, spacing=2)
        
        # Полоса прогресса на всю ширину (пока статичная на 30%)
        self.progress_bar = MDProgressBar(value=30, size_hint_y=None, height=4)
        self.mini_player.add_widget(self.progress_bar)
        
        # Строка с кнопкой управления и названием трека
        player_controls = BoxLayout(orientation="horizontal", padding=0, spacing=10)
        
        self.btn_play_pause = MDIconButton(icon="play", on_release=self.toggle_play)
        self.track_label = MDLabel(text="Плеер остановлен", halign="left", valign="middle")
        self.track_label.bind(size=self.track_label.setter('text_size')) 
        
        player_controls.add_widget(self.btn_play_pause)
        player_controls.add_widget(self.track_label)
        self.mini_player.add_widget(player_controls)
        
        # Добавляем mini-плеер в самый низ главного окна
        main_layout.add_widget(self.mini_player)
        
        return main_layout

    def update_mini_player(self, file_name):
        """Обновляет текст в плеере с обрезкой до 26 символов и меняет иконку."""
        full_text = f"Сейчас играет: {file_name}"
        display_text = full_text if len(full_text) <= 26 else full_text[:23] + "..."
        
        self.track_label.text = display_text
        self.btn_play_pause.icon = "pause"
        print(f"[Плеер] Воспроизведение файла: {file_name}")

    def toggle_play(self, instance):
        """Обработчик нажатия на кнопку Плей/Пауза в мини-плеере."""
        player = getattr(self, 'current_sound', None)
        
        if self.btn_play_pause.icon == "play":
            self.btn_play_pause.icon = "pause"
            if player:
                try:
                    player.set_pause(False)  # Снимаем с паузы в ffpyplayer
                except Exception:
                    pass
            print("[Плеер] Продолжить воспроизведение")
        else:
            self.btn_play_pause.icon = "play"
            if player:
                try:
                    player.set_pause(True)   # Ставим на паузу в ffpyplayer
                except Exception:
                    pass
            print("[Плеер] Пауза")


# Полностью переписываем методы BookScreen для логики Mega и стриминга через прокси
def _patched_load_book(self, author, book_title, book_data):
    import os  
    self.ids.book_info.text = f"{author} — {book_title}"
    self.current_folder_id = book_data.get("folder_id")
    self.ids.files_container.clear_widgets()

    # 1. ЗАГРУЗКА ОПИСАНИЯ (Ищем pattern2.txt локально)
    desc_text = "Описание на модерации..."
    if os.path.exists("pattern2.txt"):
        try:
            with open("pattern2.txt", "r", encoding="utf-8") as f:
                desc_text = f.read()
        except Exception as e:
            print(f"[Файл] Ошибка чтения локального описания: {e}")
    self.ids.book_desc.text = desc_text

    # 2. ЗАГРУЗКА ОБЛОЖКИ (Ищем pattern1.jpg локально)
    if os.path.exists("pattern1.jpg"):
        self.ids.book_cover.source = "pattern1.jpg"

    # Ищем файлы книги в каталоге
    files_data = book_data.get("files", book_data)
    if isinstance(files_data, dict):
        files = [k for k in files_data.keys() if k != "folder_id"]
    elif isinstance(files_data, list):
        files = files_data
    else:
        files = []

    if not files:
        item = OneLineListItem(text="Файлы не найдены")
        self.ids.files_container.add_widget(item)
        return

    # Выводим в список только MP3 файлы, обрезая длину строк до 26 символов
    for file_name in sorted(files):
        if not str(file_name).lower().endswith('.mp3'):
            continue
            
        item_text = f"🎵 {file_name}"
        display_text = item_text if len(item_text) <= 26 else item_text[:23] + "..."
        
        item = OneLineListItem(text=display_text)
        item.bind(on_release=lambda x, f=file_name: self.play_file(f))
        self.ids.files_container.add_widget(item)


def _patched_play_file(self, file_name):
    from network import get_mega_session
    mega = get_mega_session()
    
    if not mega:
        print("[Ошибка] Нет активной сессии Mega.")
        return

    print(f"[Mega] Запрос аудиопотока для: {file_name}")
    
    try:
        # 1. Забираем ВСЕ файлы из вашей учетной записи Mega
        all_files = mega.get_files()
        file_data = None
        
        # 2. Ищем нужный файл, проверяя имя и ID родительской папки (p)
        for node_id, node_data in all_files.items():
            if node_data.get('p') == self.current_folder_id:
                if node_data.get('a', {}).get('n') == file_name:
                    file_data = node_data
                    break
        
        if file_data:
            # Вытаскиваем хэндл (h) и ключ шифрования (k) для передачи в прокси
            file_h = file_data.get('h')
            file_k = file_data.get('k')             
            
            # Безопасно кодируем хэндл и ключ, чтобы спецсимволы не ломали URL
            from urllib.parse import quote
            safe_h = quote(str(file_h))
            safe_k = quote(str(file_k))
            
            # Собираем ссылку на наш локальный прокси-сервер ПОЛНОСТЬЮ
            local_stream_url = f"http://127.0.0.1:9999/?h={safe_h}&k={safe_k}"            
            
            print(f"[Плеер] Ссылка сформирована. Отправляем в звуковой движок.")
            
            # Обновляем текст на панели плеера внизу
            app = MDApp.get_running_app()
            app.update_mini_player(file_name)
            
            # Запускаем ffpyplayer напрямую в обход ограничений SoundLoader
            from ffpyplayer.player import MediaPlayer
            
            # Если уже играет прошлый трек — закрываем его сессию
            if hasattr(app, 'current_sound') and app.current_sound:
                try:
                    app.current_sound.close()
                except Exception:
                    pass
            
            # Передаем локальный HTTP-URL напрямую в MediaPlayer ffpyplayer
            app.current_sound = MediaPlayer(local_stream_url)
            print("[Плеер] Поток успешно передан напрямую в MediaPlayer ffpyplayer!")
        else:
            print(f"[Mega] Файл {file_name} не найден в облаке.")
            
    except Exception as e:
        print(f"[Mega] Ошибка при формировании потока: {e}")


# Намертво привязываем новые методы к классу BookScreen
BookScreen.load_book = _patched_load_book
BookScreen.play_file = _patched_play_file


if __name__ == "__main__":
    GuestPlayerApp().run()