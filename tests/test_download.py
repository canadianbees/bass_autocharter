from src.download import is_url, download_audio
import os

if __name__ == '__main__':

    output_dir = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output"
    os.makedirs(output_dir, exist_ok=True)

    path, title = download_audio("https://www.youtube.com/watch?v=iOSx9CzoIxA", output_dir)
    print(f"Downloaded: {title}")
    print(f"File: {path}")