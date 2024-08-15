import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def process_images_with_threads(image_files, operation):
    max_threads = int(os.cpu_count() * 0.8)
    if max_threads < 1:
        max_threads = 1

    with ThreadPoolExecutor(max_threads) as executor:
        futures = [executor.submit(operation, image_file) for image_file in image_files]

        for future in as_completed(futures):
            try:
                future.result()  # 確保異常被拋出
                # 成功完成任務
            except Exception as e:
                print(f"Error during image processing: {e}")
                # 你可以考慮在此處添加更多錯誤處理邏輯
