"""儿童常见可视化词表：用于离线选词的“可视化先验”和占位图片。

每项：lemma -> (类型, emoji, 中文释义)。正式配图上线后，emoji 只用于开发和兜底。
"""

VISUAL_LEXICON: dict[str, tuple[str, str, str]] = {
    # 天气 / 自然
    "rain": ("verb", "🌧️", "下雨"), "sun": ("noun", "☀️", "太阳"), "cloud": ("noun", "☁️", "云"),
    "snow": ("noun", "❄️", "雪"), "wind": ("noun", "🌬️", "风"), "rainbow": ("noun", "🌈", "彩虹"),
    "puddle": ("noun", "💧", "水坑"), "mud": ("noun", "🟤", "泥巴"), "muddy": ("adj", "🟫", "满是泥的"),
    "tree": ("noun", "🌳", "树"), "flower": ("noun", "🌸", "花"), "grass": ("noun", "🌱", "草"),
    "hill": ("noun", "⛰️", "小山"), "sea": ("noun", "🌊", "大海"), "star": ("noun", "⭐", "星星"),
    "moon": ("noun", "🌙", "月亮"), "leaf": ("noun", "🍃", "树叶"), "water": ("noun", "💦", "水"),
    "garden": ("noun", "🏡", "花园"), "outside": ("other", "🏞️", "在外面"),
    # 衣物
    "boot": ("noun", "🥾", "靴子"), "boots": ("noun", "🥾", "靴子"), "hat": ("noun", "👒", "帽子"),
    "coat": ("noun", "🧥", "外套"), "raincoat": ("noun", "🧥", "雨衣"), "sock": ("noun", "🧦", "袜子"),
    "shoe": ("noun", "👟", "鞋"), "dress": ("noun", "👗", "连衣裙"), "glasses": ("noun", "👓", "眼镜"),
    "umbrella": ("noun", "☂️", "雨伞"),
    # 家庭 / 人物
    "mummy": ("noun", "👩", "妈妈"), "mommy": ("noun", "👩", "妈妈"), "daddy": ("noun", "👨", "爸爸"),
    "baby": ("noun", "👶", "宝宝"), "brother": ("noun", "👦", "哥哥/弟弟"), "sister": ("noun", "👧", "姐姐/妹妹"),
    "grandpa": ("noun", "👴", "爷爷/外公"), "granny": ("noun", "👵", "奶奶/外婆"), "friend": ("noun", "🧑‍🤝‍🧑", "朋友"),
    "teacher": ("noun", "🧑‍🏫", "老师"),
    # 动物
    "pig": ("noun", "🐷", "猪"), "dog": ("noun", "🐶", "狗"), "cat": ("noun", "🐱", "猫"),
    "rabbit": ("noun", "🐰", "兔子"), "sheep": ("noun", "🐑", "羊"), "duck": ("noun", "🦆", "鸭子"),
    "horse": ("noun", "🐴", "马"), "cow": ("noun", "🐮", "奶牛"), "bird": ("noun", "🐦", "鸟"),
    "fish": ("noun", "🐟", "鱼"), "dinosaur": ("noun", "🦖", "恐龙"), "frog": ("noun", "🐸", "青蛙"),
    "elephant": ("noun", "🐘", "大象"), "zebra": ("noun", "🦓", "斑马"), "bee": ("noun", "🐝", "蜜蜂"),
    "butterfly": ("noun", "🦋", "蝴蝶"), "snail": ("noun", "🐌", "蜗牛"), "owl": ("noun", "🦉", "猫头鹰"),
    # 家里 / 物品
    "house": ("noun", "🏠", "房子"), "bed": ("noun", "🛏️", "床"), "bath": ("noun", "🛁", "洗澡/浴缸"),
    "door": ("noun", "🚪", "门"), "window": ("noun", "🪟", "窗户"), "chair": ("noun", "🪑", "椅子"),
    "table": ("noun", "🍽️", "桌子"), "car": ("noun", "🚗", "汽车"), "bus": ("noun", "🚌", "公共汽车"),
    "train": ("noun", "🚂", "火车"), "boat": ("noun", "⛵", "船"), "plane": ("noun", "✈️", "飞机"),
    "bike": ("noun", "🚲", "自行车"), "ball": ("noun", "⚽", "球"), "kite": ("noun", "🪁", "风筝"),
    "book": ("noun", "📖", "书"), "toy": ("noun", "🧸", "玩具"), "teddy": ("noun", "🧸", "泰迪熊"),
    "box": ("noun", "📦", "盒子"), "balloon": ("noun", "🎈", "气球"), "present": ("noun", "🎁", "礼物"),
    "clock": ("noun", "⏰", "钟"), "phone": ("noun", "📱", "电话"), "computer": ("noun", "💻", "电脑"),
    "picture": ("noun", "🖼️", "图画"), "camera": ("noun", "📷", "相机"), "key": ("noun", "🔑", "钥匙"),
    "bag": ("noun", "🎒", "包"), "bucket": ("noun", "🪣", "水桶"), "spade": ("noun", "🪏", "铲子"),
    "swing": ("noun", "🛝", "秋千"), "slide": ("noun", "🛝", "滑梯"), "drum": ("noun", "🥁", "鼓"),
    "school": ("noun", "🏫", "学校"), "playground": ("noun", "🛝", "游乐场"), "shop": ("noun", "🏪", "商店"),
    # 食物
    "apple": ("noun", "🍎", "苹果"), "banana": ("noun", "🍌", "香蕉"), "cake": ("noun", "🍰", "蛋糕"),
    "cookie": ("noun", "🍪", "饼干"), "biscuit": ("noun", "🍪", "饼干"), "ice cream": ("noun", "🍦", "冰淇淋"),
    "milk": ("noun", "🥛", "牛奶"), "juice": ("noun", "🧃", "果汁"), "bread": ("noun", "🍞", "面包"),
    "egg": ("noun", "🥚", "鸡蛋"), "carrot": ("noun", "🥕", "胡萝卜"), "pizza": ("noun", "🍕", "披萨"),
    "spaghetti": ("noun", "🍝", "意大利面"), "cheese": ("noun", "🧀", "奶酪"), "tea": ("noun", "🍵", "茶"),
    "breakfast": ("noun", "🥣", "早餐"), "dinner": ("noun", "🍽️", "晚餐"), "lunch": ("noun", "🥪", "午餐"),
    "pumpkin": ("noun", "🎃", "南瓜"), "tomato": ("noun", "🍅", "西红柿"),
    # 动作
    "jump": ("verb", "🦘", "跳"), "splash": ("verb", "💦", "溅水"), "run": ("verb", "🏃", "跑"),
    "walk": ("verb", "🚶", "走"), "swim": ("verb", "🏊", "游泳"), "dance": ("verb", "💃", "跳舞"),
    "sing": ("verb", "🎤", "唱歌"), "sleep": ("verb", "😴", "睡觉"), "eat": ("verb", "😋", "吃"),
    "drink": ("verb", "🥤", "喝"), "laugh": ("verb", "😂", "笑"), "cry": ("verb", "😢", "哭"),
    "play": ("verb", "🤸", "玩"), "fly": ("verb", "🕊️", "飞"), "climb": ("verb", "🧗", "爬"),
    "fall": ("verb", "🤕", "摔倒"), "kick": ("verb", "🦵", "踢"), "throw": ("verb", "🤾", "扔"),
    "catch": ("verb", "🫴", "接住"), "wash": ("verb", "🧼", "洗"), "brush": ("verb", "🪥", "刷"),
    "read": ("verb", "📚", "读"), "draw": ("verb", "🖍️", "画"), "paint": ("verb", "🎨", "涂色"),
    "cook": ("verb", "🧑‍🍳", "做饭"), "hide": ("verb", "🙈", "躲"), "clap": ("verb", "👏", "拍手"),
    "wave": ("verb", "👋", "挥手"), "hug": ("verb", "🤗", "拥抱"), "snore": ("verb", "😪", "打鼾"),
    "wear": ("verb", "🧥", "穿"), "ride": ("verb", "🚴", "骑"), "push": ("verb", "🫸", "推"),
    "pull": ("verb", "🫷", "拉"), "open": ("verb", "📂", "打开"), "close": ("verb", "🚪", "关上"),
    "look": ("verb", "👀", "看"), "listen": ("verb", "👂", "听"), "build": ("verb", "🧱", "搭建"),
    # 形容词
    "big": ("adj", "🐘", "大的"), "little": ("adj", "🐭", "小的"), "small": ("adj", "🐭", "小的"),
    "wet": ("adj", "💦", "湿的"), "dry": ("adj", "🌵", "干的"), "dirty": ("adj", "🟫", "脏的"),
    "clean": ("adj", "✨", "干净的"), "hot": ("adj", "🔥", "热的"), "cold": ("adj", "🥶", "冷的"),
    "happy": ("adj", "😄", "开心的"), "sad": ("adj", "😢", "难过的"), "angry": ("adj", "😠", "生气的"),
    "tired": ("adj", "🥱", "累的"), "hungry": ("adj", "🤤", "饿的"), "scared": ("adj", "😨", "害怕的"),
    "red": ("adj", "🔴", "红色的"), "blue": ("adj", "🔵", "蓝色的"), "yellow": ("adj", "🟡", "黄色的"),
    "green": ("adj", "🟢", "绿色的"), "pink": ("adj", "🩷", "粉色的"), "loud": ("adj", "📢", "大声的"),
    "fast": ("adj", "⚡", "快的"), "slow": ("adj", "🐢", "慢的"), "tall": ("adj", "🦒", "高的"),
}

# 常见可场景化的短语（离线兜底用）
PHRASE_LEXICON: dict[str, tuple[str, str]] = {
    "jump up and down": ("🦘", "上下蹦跳"), "jumping up and down": ("🦘", "上下蹦跳"),
    "go to bed": ("🛏️", "上床睡觉"), "time for bed": ("🛏️", "该睡觉了"), "wake up": ("⏰", "醒来"),
    "let's go": ("🏃", "我们走吧"), "look at me": ("🙋", "看我"), "i'm hungry": ("🤤", "我饿了"),
    "put on": ("🧥", "穿上"), "take off": ("🧦", "脱下"), "sit down": ("🪑", "坐下"),
    "stand up": ("🧍", "站起来"), "come here": ("👋", "过来"), "fall over": ("🤕", "摔倒"),
    "go outside": ("🏞️", "出去"), "play outside": ("🏞️", "在外面玩"), "have a bath": ("🛁", "洗澡"),
    "clean up": ("🧹", "打扫"), "well done": ("👏", "做得好"), "thank you": ("🙏", "谢谢"),
    "good night": ("🌙", "晚安"), "good morning": ("🌅", "早上好"), "hide and seek": ("🙈", "捉迷藏"),
    "muddy puddle": ("💧", "泥水坑"), "wear your boots": ("🥾", "穿上靴子"),
}

STOPWORDS = set(
    """a about above after again against all am an and any are aren't as at be because been before being below
    between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few
    for from further get got had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself
    him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself just let let's me more most
    mustn't must my myself no nor not now of off on once only or other ought our ours ourselves out over own same
    shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then
    there there's these they they'd they'll they're they've this those through to too under until up very was wasn't
    we we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's
    will with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves oh yes yeah okay ok
    hello hi bye goodbye please thanks thank really very well also again today tomorrow yesterday now soon always
    never maybe one two three lot lots thing things something anything everything nothing everyone someone way
    like love loves want wants go goes going gone went come comes coming came say says said see sees saw know knows
    think thinks make makes made take takes took give gives gave tell tells told shall may might need needs much many
    bit right good great best better ha hee ooh ah uh um hmm wow""".split()
)
