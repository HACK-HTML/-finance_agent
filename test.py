# 模拟内容块对象
class MockBlock:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class Extractor:
    def _extract_text(self, content_blocks: list) -> str:
        texts = [b.text for b in content_blocks if hasattr(b, "text")]
        return "\t".join(texts) if texts else "（无文本输出）"

extractor = Extractor()

# 场景 1：包含多个 text 块（证明不会只取最后一个）
blocks_multiple_texts = [
    MockBlock(text="这是第一段文本。"),
    MockBlock(text="这是第二段文本。"),
    MockBlock(text="这是第三段文本。")
]
print(extractor._extract_text(blocks_multiple_texts))
# 输出:
# 这是第一段文本。
# 这是第二段文本。
# 这是第三段文本。

# 场景 2：混合块（包含无 text 属性的块，如图像或工具调用）
blocks_mixed = [
    MockBlock(text="这是文本块。"),
    MockBlock(image_url="http://example.com/image.png"), # 无 text 属性
    MockBlock(tool_call={"name": "search"}),             # 无 text 属性
    MockBlock(text="这是总结文本。")
]
print(extractor._extract_text(blocks_mixed))
# 输出:
# 这是文本块。
# 这是总结文本。

# 场景 3：完全没有 text 块或列表为空
blocks_empty = [
    MockBlock(image_url="http://example.com/image.png")
]
print(extractor._extract_text(blocks_empty))
# 输出:
# （无文本输出）