# threading_executor.py
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# threading_executor.py
def process_images_with_threads(tasks, operation):
    """
    tasks: list[tuple] → (input_folder, output_folder, filename)
    operation: 函式，參數會用 *task 展開
    """
    if not tasks:
        return []

    results = []
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(operation, *task)  # ★ 參數解包
                   for task in tasks]
        for f in as_completed(futures):
            results.append(f.result())
    return results

