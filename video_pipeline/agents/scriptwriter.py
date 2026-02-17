"""Scriptwriter Agent - Generates scene-by-scene video scripts from content plans.

Uses template-based generation (no LLM required) since baby content
follows well-established, formulaic patterns. Each video type has its
own script generator that creates structured ScriptScene sequences
with narration, visual descriptions, and timing.

All lyrics used are in the public domain.
"""

from __future__ import annotations

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import (
    ContentPlan,
    PipelineContext,
    Script,
    ScriptScene,
    VideoType,
)

# ---------------------------------------------------------------------------
# Color name -> hex mapping for element colors
# ---------------------------------------------------------------------------
COLOR_HEX: dict[str, str] = {
    "red": "#FF0000",
    "blue": "#0000FF",
    "yellow": "#FFD700",
    "green": "#00AA00",
    "orange": "#FF8C00",
    "purple": "#800080",
    "pink": "#FF69B4",
    "brown": "#8B4513",
    "black": "#000000",
    "white": "#FFFFFF",
    "gray": "#808080",
    "gold": "#FFD700",
}

# ---------------------------------------------------------------------------
# Alphabet -> example word mapping (common baby-friendly words)
# ---------------------------------------------------------------------------
ALPHABET_WORDS: dict[str, str] = {
    "A": "Apple",
    "B": "Ball",
    "C": "Cat",
    "D": "Dog",
    "E": "Elephant",
    "F": "Fish",
    "G": "Grape",
    "H": "Hat",
    "I": "Ice cream",
    "J": "Jellyfish",
    "K": "Kite",
    "L": "Lion",
    "M": "Moon",
    "N": "Nest",
    "O": "Orange",
    "P": "Penguin",
    "Q": "Queen",
    "R": "Rainbow",
    "S": "Star",
    "T": "Turtle",
    "U": "Umbrella",
    "V": "Violin",
    "W": "Whale",
    "X": "Xylophone",
    "Y": "Yarn",
    "Z": "Zebra",
}

# ---------------------------------------------------------------------------
# Animal -> sound mapping
# ---------------------------------------------------------------------------
ANIMAL_SOUNDS: dict[str, str] = {
    "cow": "Moo",
    "pig": "Oink",
    "chicken": "Cluck cluck",
    "horse": "Neigh",
    "sheep": "Baa",
    "duck": "Quack",
    "lion": "Roar",
    "elephant": "Trumpet",
    "monkey": "Ooh ooh ah ah",
    "giraffe": "Hum",
    "zebra": "Bark",
    "fish": "Blub blub",
    "whale": "Woooo",
    "dolphin": "Click click",
    "turtle": "Snap",
    "octopus": "Swoosh",
    "dog": "Woof",
    "cat": "Meow",
    "bird": "Tweet tweet",
    "rabbit": "Squeak",
    "hamster": "Squeak squeak",
    "frog": "Ribbit",
    "bee": "Buzz",
    "owl": "Hoot",
    "rooster": "Cock-a-doodle-doo",
    "goat": "Meh",
    "donkey": "Hee-haw",
}

# ---------------------------------------------------------------------------
# Public-domain nursery rhyme lyrics
# ---------------------------------------------------------------------------
NURSERY_LYRICS: dict[str, list[str]] = {
    "Mary Had a Little Lamb": [
        "Mary had a little lamb, little lamb, little lamb,\n"
        "Mary had a little lamb, its fleece was white as snow.",
        "And everywhere that Mary went, Mary went, Mary went,\n"
        "Everywhere that Mary went, the lamb was sure to go.",
        "It followed her to school one day, school one day, school one day,\n"
        "It followed her to school one day, which was against the rules.",
        "It made the children laugh and play, laugh and play, laugh and play,\n"
        "It made the children laugh and play, to see a lamb at school.",
    ],
    "Baa Baa Black Sheep": [
        "Baa, baa, black sheep, have you any wool?\n"
        "Yes sir, yes sir, three bags full.",
        "One for the master, one for the dame,\n"
        "And one for the little boy who lives down the lane.",
        "Baa, baa, black sheep, have you any wool?\n"
        "Yes sir, yes sir, three bags full.",
    ],
    "Humpty Dumpty": [
        "Humpty Dumpty sat on a wall,\n"
        "Humpty Dumpty had a great fall.",
        "All the king's horses and all the king's men\n"
        "Couldn't put Humpty together again.",
    ],
    "Jack and Jill": [
        "Jack and Jill went up the hill\n"
        "To fetch a pail of water.",
        "Jack fell down and broke his crown,\n"
        "And Jill came tumbling after.",
        "Up Jack got, and home did trot,\n"
        "As fast as he could caper.",
        "He went to bed to mend his head\n"
        "With vinegar and brown paper.",
    ],
    "Itsy Bitsy Spider": [
        "The itsy bitsy spider climbed up the water spout.\n"
        "Down came the rain and washed the spider out.",
        "Out came the sun and dried up all the rain,\n"
        "And the itsy bitsy spider climbed up the spout again.",
    ],
    "Old MacDonald Had a Farm": [
        "Old MacDonald had a farm, E-I-E-I-O!\n"
        "And on his farm he had a cow, E-I-E-I-O!",
        "With a moo-moo here and a moo-moo there,\n"
        "Here a moo, there a moo, everywhere a moo-moo.",
        "Old MacDonald had a farm, E-I-E-I-O!\n"
        "And on his farm he had a pig, E-I-E-I-O!",
        "With an oink-oink here and an oink-oink there,\n"
        "Here an oink, there an oink, everywhere an oink-oink.",
        "Old MacDonald had a farm, E-I-E-I-O!\n"
        "And on his farm he had a duck, E-I-E-I-O!",
        "With a quack-quack here and a quack-quack there,\n"
        "Here a quack, there a quack, everywhere a quack-quack.",
    ],
    "Row Row Row Your Boat": [
        "Row, row, row your boat,\n"
        "Gently down the stream.",
        "Merrily, merrily, merrily, merrily,\n"
        "Life is but a dream.",
        "Row, row, row your boat,\n"
        "Gently down the stream.",
        "If you see a crocodile,\n"
        "Don't forget to scream!",
    ],
    "Head Shoulders Knees and Toes": [
        "Head, shoulders, knees and toes, knees and toes.\n"
        "Head, shoulders, knees and toes, knees and toes.",
        "And eyes, and ears, and mouth, and nose.\n"
        "Head, shoulders, knees and toes, knees and toes.",
        "Head, shoulders, knees and toes, knees and toes.\n"
        "Head, shoulders, knees and toes, knees and toes.",
        "And eyes, and ears, and mouth, and nose.\n"
        "Head, shoulders, knees and toes, knees and toes.",
    ],
}

# ---------------------------------------------------------------------------
# Public-domain lullaby lyrics
# ---------------------------------------------------------------------------
LULLABY_LYRICS: dict[str, list[str]] = {
    "Twinkle Twinkle Little Star": [
        "Twinkle, twinkle, little star,\n"
        "How I wonder what you are.",
        "Up above the world so high,\n"
        "Like a diamond in the sky.",
        "Twinkle, twinkle, little star,\n"
        "How I wonder what you are.",
        "When the blazing sun is gone,\n"
        "When he nothing shines upon.",
        "Then you show your little light,\n"
        "Twinkle, twinkle, all the night.",
        "Twinkle, twinkle, little star,\n"
        "How I wonder what you are.",
    ],
    "Rock-a-Bye Baby": [
        "Rock-a-bye baby, on the treetop,\n"
        "When the wind blows, the cradle will rock.",
        "When the bough breaks, the cradle will fall,\n"
        "And down will come baby, cradle and all.",
        "Baby is drowsing, cozy and fair,\n"
        "Mother sits near in her rocking chair.",
        "Forward and back, the cradle she swings,\n"
        "And though baby sleeps, he hears what she sings.",
    ],
    "Hush Little Baby": [
        "Hush, little baby, don't say a word,\n"
        "Mama's gonna buy you a mockingbird.",
        "And if that mockingbird won't sing,\n"
        "Mama's gonna buy you a diamond ring.",
        "And if that diamond ring turns brass,\n"
        "Mama's gonna buy you a looking glass.",
        "And if that looking glass gets broke,\n"
        "Mama's gonna buy you a billy goat.",
        "And if that billy goat won't pull,\n"
        "Mama's gonna buy you a cart and bull.",
        "And if that cart and bull turn over,\n"
        "Mama's gonna buy you a dog named Rover.",
        "And if that dog named Rover won't bark,\n"
        "Mama's gonna buy you a horse and cart.",
        "And if that horse and cart fall down,\n"
        "You'll still be the sweetest little baby in town.",
    ],
    "Brahms Lullaby": [
        "Lullaby and good night, with roses bedight,\n"
        "With lilies o'er spread is baby's wee bed.",
        "Lay thee down now and rest, may thy slumber be blessed,\n"
        "Lay thee down now and rest, may thy slumber be blessed.",
        "Lullaby and good night, thy mother's delight,\n"
        "Bright angels beside my darling abide.",
        "They will guard thee at rest, thou shalt wake on my breast,\n"
        "They will guard thee at rest, thou shalt wake on my breast.",
    ],
    "All the Pretty Horses": [
        "Hush-a-bye, don't you cry,\n"
        "Go to sleep, little baby.",
        "When you wake, you shall have\n"
        "All the pretty little horses.",
        "Blacks and bays, dapples and grays,\n"
        "All the pretty little horses.",
        "Hush-a-bye, don't you cry,\n"
        "Go to sleep, little baby.",
    ],
}

# ---------------------------------------------------------------------------
# Anime dance scene data
# ---------------------------------------------------------------------------

# Dark neon backgrounds for the Tokyo night aesthetic
NEON_BACKGROUNDS: list[str] = [
    "#0a0a1a",  # Deep night
    "#0d0d2b",  # Midnight blue
    "#120821",  # Dark violet night
    "#0b1121",  # Deep navy
    "#10061a",  # Dark purple
    "#0a0f1e",  # Ink blue
    "#0e0a1f",  # Deep plum night
    "#080d1a",  # Blackened blue
]

# Neon accent colors for signs, reflections, and lighting
NEON_ACCENTS: list[str] = [
    "#FF00FF",  # Magenta
    "#00FFFF",  # Cyan
    "#FF1493",  # Deep pink
    "#00FF7F",  # Spring green
    "#FF6347",  # Tomato neon
    "#7B68EE",  # Medium slate blue
    "#FFD700",  # Gold
    "#FF4500",  # Neon orange
]

# Dance poses described for each scene beat
DANCE_POSES: list[dict[str, str]] = [
    {"pose": "arms_raised", "desc": "Arms raised high with weight on back foot, hair flowing upward"},
    {"pose": "body_wave", "desc": "Fluid body wave rolling from chest to knees, jacket rippling"},
    {"pose": "side_step", "desc": "Sharp side-step freeze with one arm extended, fingers spread"},
    {"pose": "spin", "desc": "Mid-spin with hair and clothing trailing in a spiral arc"},
    {"pose": "lean_back", "desc": "Deep lean-back with one hand on hat, other arm sweeping low"},
    {"pose": "pop_lock", "desc": "Popping chest hit with arms locked at right angles"},
    {"pose": "groove_bounce", "desc": "Relaxed bounce with shoulders rolling, head nodding to the beat"},
    {"pose": "slide_glide", "desc": "Smooth glide-step across the floor, trailing neon reflections"},
    {"pose": "kick_out", "desc": "Dynamic kick-out with opposite arm swing, jacket flaring"},
    {"pose": "final_pose", "desc": "Confident final stance, one hand pointing skyward, city lights blazing behind"},
]

# Setting descriptions
SETTING_VISUALS: dict[str, str] = {
    "tokyo_balcony": (
        "A wide Tokyo balcony overlooking a dense cityscape at night. "
        "Neon signs in Japanese katakana glow pink, cyan, and gold below. "
        "The railing catches reflections from the city lights."
    ),
    "neon_rooftop": (
        "A rooftop terrace high above the Tokyo skyline. "
        "Giant LED billboards flash in the distance. "
        "Puddles from recent rain mirror the neon glow."
    ),
    "shibuya_crossing": (
        "The iconic Shibuya crossing at midnight, empty and lit by "
        "towering video screens. Crosswalk lines glow faintly. "
        "Rain-slicked asphalt reflects every color."
    ),
    "akihabara_street": (
        "A narrow Akihabara side street bathed in electric signage. "
        "Vending machines cast blue and orange light. "
        "Cables criss-cross overhead between buildings."
    ),
}

# Dark background colors used for lullaby scenes
LULLABY_BACKGROUNDS: list[str] = [
    "#1a1a2e",
    "#16213e",
    "#0f3460",
    "#1b1b2f",
    "#162447",
    "#1f1f38",
    "#1a1a3e",
    "#0d1b2a",
]


class ScriptwriterAgent(BaseAgent):
    """Generates scene-by-scene video scripts from content plans.

    Uses template-based generation rather than an LLM because baby
    educational content follows highly formulaic, repeatable patterns.
    Each video type has a dedicated script generator that produces
    properly timed scenes with narration text, visual descriptions,
    background colors, on-screen elements, and transitions.

    Supported video types:
        - COUNTING: Number sequences with object visuals
        - COLORS: Color introduction and repetition
        - SHAPES: Shape identification and naming
        - ALPHABET: Letter-word association (A is for Apple)
        - ANIMALS: Animal names paired with sounds
        - LULLABY: Soft verse repetition for sleep content
        - NURSERY_RHYME: Classic public-domain children's songs
    """

    @property
    def name(self) -> str:
        """Unique name for this agent."""
        return "scriptwriter"

    @property
    def completion_event_type(self) -> EventType:
        """Event type to publish when script writing completes."""
        return EventType.SCRIPT_WRITTEN

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Generate a complete video script from the content plan.

        Reads the plan from *context.plan*, dispatches to the
        appropriate type-specific script generator, calculates total
        duration, attaches the finished ``Script`` to
        *context.script*, and returns the updated context.

        Raises:
            ValueError: If no content plan is present in the context.
        """
        plan: ContentPlan | None = context.plan
        if plan is None:
            raise ValueError(
                "No content plan found in context - planner agent must run first"
            )

        # Dispatch to the correct generator based on video type
        generators = {
            VideoType.COUNTING: self._generate_counting_script,
            VideoType.COLORS: self._generate_colors_script,
            VideoType.SHAPES: self._generate_shapes_script,
            VideoType.ALPHABET: self._generate_alphabet_script,
            VideoType.ANIMALS: self._generate_animals_script,
            VideoType.LULLABY: self._generate_lullaby_script,
            VideoType.NURSERY_RHYME: self._generate_nursery_rhyme_script,
            VideoType.ANIME_DANCE: self._generate_anime_dance_script,
        }

        generator = generators.get(plan.video_type)
        if generator is None:
            raise ValueError(f"Unsupported video type: {plan.video_type}")

        scenes = generator(plan)

        # Calculate total duration
        total_duration = sum(scene.duration_seconds for scene in scenes)

        # Build the Script model
        voice_style = (
            "calm" if plan.video_type == VideoType.LULLABY
            else "energetic" if plan.video_type == VideoType.ANIME_DANCE
            else "cheerful"
        )
        music_style = (
            "calm"
            if plan.video_type == VideoType.LULLABY
            else "city_pop"
            if plan.video_type == VideoType.ANIME_DANCE
            else "playful"
            if plan.video_type == VideoType.NURSERY_RHYME
            else "upbeat"
        )

        script = Script(
            video_id=plan.video_id,
            video_type=plan.video_type,
            title=plan.title_working,
            scenes=scenes,
            total_duration_seconds=total_duration,
            voice_style=voice_style,
            music_style=music_style,
        )

        context.script = script
        self.logger.info(
            "Script written: %s (%d scenes, %.0fs total, voice=%s)",
            script.title,
            len(script.scenes),
            script.total_duration_seconds,
            script.voice_style,
        )
        return context

    # ------------------------------------------------------------------
    # Helper: cycle through configured bright background colors
    # ------------------------------------------------------------------

    def _bg_color(self, index: int) -> str:
        """Return a background color by cycling through the configured palette."""
        colors = self.config.visual.background_colors
        return colors[index % len(colors)]

    # ------------------------------------------------------------------
    # COUNTING script generator
    # ------------------------------------------------------------------

    def _generate_counting_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for a counting video.

        Structure:
            1. Intro scene welcoming the viewer
            2. One scene per number with narration and visual element
            3. Outro scene with positive reinforcement
        """
        details = plan.topic_details
        start: int = details.get("start", 1)
        end: int = details.get("end", 10)
        step: int = details.get("step", 1)
        objects: str = details.get("objects", "stars")

        scenes: list[ScriptScene] = []
        scene_num = 1

        # Intro scene
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text=f"Let's count {objects}! Are you ready?",
                visual_description=(
                    f"A cheerful 3D animated nursery room with colorful {objects} "
                    f"floating in from the sides, bright playful atmosphere, "
                    f"soft pastel colors, welcoming scene for toddlers"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": f"Let's Count {objects.title()}!", "color": "#FFFFFF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # Number scenes
        numbers = list(range(start, end + (1 if step > 0 else -1), step))
        for i, number in enumerate(numbers):
            obj_label = objects if number != 1 else objects.rstrip("s")
            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=5.0,
                    narration_text=f"{number}! {number} {obj_label}!",
                    visual_description=(
                        f"A cute 3D animated scene with a large colorful number "
                        f"'{number}' in the center, surrounded by {number} adorable "
                        f"3D cartoon {objects}, soft pastel nursery background, "
                        f"cheerful playful atmosphere for toddlers"
                    ),
                    background_color=self._bg_color(i + 1),
                    elements=[
                        {"type": "number", "value": str(number), "color": COLOR_HEX.get("red", "#FF0000")},
                        {"type": "object", "value": objects, "count": number, "color": "#FFFFFF"},
                    ],
                    transition="fade",
                )
            )
            scene_num += 1

        # Outro scene
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=7.0,
                narration_text="Great job! You counted so well! See you next time!",
                visual_description=(
                    "A joyful 3D animated celebration scene with colorful confetti, "
                    "balloons, and sparkles, adorable cartoon characters cheering, "
                    "bright cheerful nursery room background"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": "Great Job!", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # COLORS script generator
    # ------------------------------------------------------------------

    def _generate_colors_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for a colors video.

        Structure:
            1. Intro scene
            2. One scene per color with interactive narration
            3. Outro scene
        """
        details = plan.topic_details
        colors: list[str] = details.get("colors", ["red", "blue", "yellow", "green"])

        scenes: list[ScriptScene] = []
        scene_num = 1

        # Intro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text="Let's learn colors! So many beautiful colors to see!",
                visual_description=(
                    "A beautiful 3D animated rainbow swirl with all colors "
                    "of the rainbow spiraling together, bright cheerful "
                    "nursery room background, inviting and fun"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": "Let's Learn Colors!", "color": "#FFFFFF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # Color scenes
        for i, color in enumerate(colors):
            hex_color = COLOR_HEX.get(color, "#FF0000")
            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=7.0,
                    narration_text=f"This is {color}! Can you say {color}?",
                    visual_description=(
                        f"A cute 3D animated scene filled with {color} colored objects, "
                        f"adorable {color} 3D toys and decorations, a friendly cartoon "
                        f"character presenting the color, soft glowing {color} background"
                    ),
                    background_color=hex_color,
                    elements=[
                        {"type": "color_swatch", "value": color, "color": hex_color},
                        {"type": "text", "value": color.upper(), "color": "#FFFFFF"},
                    ],
                    transition="fade",
                )
            )
            scene_num += 1

        # Outro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=7.0,
                narration_text="Great job! You learned so many colors! See you next time!",
                visual_description=(
                    "A joyful 3D animated celebration with a beautiful rainbow arc, "
                    "colorful confetti and balloons, adorable cartoon characters "
                    "celebrating, bright cheerful atmosphere"
                ),
                background_color=self._bg_color(1),
                elements=[
                    {"type": "text", "value": "Great Job!", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # SHAPES script generator
    # ------------------------------------------------------------------

    def _generate_shapes_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for a shapes video.

        Structure:
            1. Intro scene
            2. One scene per shape with name and description
            3. Outro scene
        """
        details = plan.topic_details
        shapes: list[str] = details.get(
            "shapes", ["circle", "square", "triangle", "rectangle"]
        )

        # Shape -> number of sides for educational detail
        shape_descriptions: dict[str, str] = {
            "circle": "round and smooth with no corners",
            "square": "has four equal sides",
            "triangle": "has three sides and three corners",
            "rectangle": "has two long sides and two short sides",
            "star": "has five shiny points",
            "heart": "shaped like love",
            "diamond": "a square turned sideways",
            "oval": "like a stretched circle",
            "pentagon": "has five sides",
            "hexagon": "has six sides",
            "octagon": "has eight sides, like a stop sign",
            "crescent": "curved like the moon",
        }

        scenes: list[ScriptScene] = []
        scene_num = 1

        # Intro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text="Let's learn shapes! Shapes are everywhere!",
                visual_description=(
                    "A colorful 3D animated playroom with various friendly "
                    "3D shapes floating and bouncing gently, soft pastel "
                    "background, warm inviting atmosphere for toddlers"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": "Let's Learn Shapes!", "color": "#FFFFFF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # Shape scenes
        for i, shape in enumerate(shapes):
            desc = shape_descriptions.get(shape, f"a special shape called {shape}")
            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=7.0,
                    narration_text=(
                        f"This is a {shape}! A {shape} is {desc}. "
                        f"Can you say {shape}?"
                    ),
                    visual_description=(
                        f"A cute 3D animated {shape} floating in the center of a "
                        f"colorful playroom, smooth glossy surface with soft shadows, "
                        f"friendly educational toy aesthetic, bright cheerful scene"
                    ),
                    background_color=self._bg_color(i + 1),
                    elements=[
                        {"type": "shape", "value": shape, "color": self._bg_color(i + 3)},
                        {"type": "text", "value": shape.upper(), "color": "#FFFFFF"},
                    ],
                    transition="fade",
                )
            )
            scene_num += 1

        # Outro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=7.0,
                narration_text="Great job! You learned all the shapes! See you next time!",
                visual_description=(
                    "A joyful 3D animated scene with all the shapes gathered "
                    "together bouncing happily, colorful confetti, bright "
                    "celebration atmosphere, cheerful nursery playroom"
                ),
                background_color=self._bg_color(2),
                elements=[
                    {"type": "text", "value": "Great Job!", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # ALPHABET script generator
    # ------------------------------------------------------------------

    def _generate_alphabet_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for an alphabet video.

        Structure:
            1. Intro scene
            2. One scene per letter with 'X is for Xylophone' pattern
            3. Outro scene
        """
        details = plan.topic_details
        start_letter: str = details.get("start", "A")
        end_letter: str = details.get("end", "Z")

        start_ord = ord(start_letter.upper())
        end_ord = ord(end_letter.upper())
        letters = [chr(o) for o in range(start_ord, end_ord + 1)]

        scenes: list[ScriptScene] = []
        scene_num = 1

        # Intro
        range_label = (
            "the alphabet"
            if start_letter == "A" and end_letter == "Z"
            else f"letters {start_letter} to {end_letter}"
        )
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text=f"Let's learn {range_label}! Ready? Let's go!",
                visual_description=(
                    f"A cheerful 3D animated scene with colorful 3D alphabet "
                    f"letters floating and bouncing, bright nursery room "
                    f"background, fun educational atmosphere for toddlers"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": f"Learn {range_label.title()}!", "color": "#FFFFFF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # Letter scenes
        for i, letter in enumerate(letters):
            word = ALPHABET_WORDS.get(letter, "Apple")
            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=6.0,
                    narration_text=f"{letter} is for {word}!",
                    visual_description=(
                        f"A cute 3D animated scene with a large colorful letter "
                        f"'{letter}' on the left and an adorable 3D cartoon "
                        f"{word.lower()} on the right, bright cheerful nursery "
                        f"background, educational and playful"
                    ),
                    background_color=self._bg_color(i + 1),
                    elements=[
                        {"type": "letter", "value": letter, "color": "#FF4444"},
                        {"type": "object", "value": word.lower(), "count": 1, "color": "#FFFFFF"},
                    ],
                    transition="fade",
                )
            )
            scene_num += 1

        # Outro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=7.0,
                narration_text="Great job! You learned your letters! See you next time!",
                visual_description=(
                    "A joyful 3D animated celebration with colorful alphabet "
                    "letters arranged in a rainbow arc, sparkling stars and "
                    "confetti, adorable cartoon characters celebrating"
                ),
                background_color=self._bg_color(3),
                elements=[
                    {"type": "text", "value": "Great Job!", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # ANIMALS script generator
    # ------------------------------------------------------------------

    def _generate_animals_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for an animals video.

        Structure:
            1. Intro scene introducing the theme
            2. One scene per animal with name and sound
            3. Outro scene
        """
        details = plan.topic_details
        theme: str = details.get("theme", "farm")
        animals: list[str] = details.get(
            "animals", ["cow", "pig", "chicken", "horse", "sheep", "duck"]
        )

        scenes: list[ScriptScene] = []
        scene_num = 1

        # Intro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text=(
                    f"Let's meet the {theme} animals! "
                    f"Do you know what sounds they make?"
                ),
                visual_description=(
                    f"A cute 3D animated {theme} scene with a colorful barn "
                    f"and green fields, adorable cartoon {theme} animals "
                    f"peeking out, sunny cheerful day, Pixar-style render"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": f"{theme.title()} Animals!", "color": "#FFFFFF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # Animal scenes
        for i, animal in enumerate(animals):
            sound = ANIMAL_SOUNDS.get(animal, "...")
            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=8.0,
                    narration_text=(
                        f"This is a {animal}! The {animal} says {sound}! "
                        f"Can you say {sound}?"
                    ),
                    visual_description=(
                        f"An adorable 3D cartoon {animal} character with big "
                        f"expressive eyes and a friendly smile, standing in a "
                        f"colorful natural setting, Pixar-style render, "
                        f"soft lighting, cute and appealing to toddlers"
                    ),
                    background_color=self._bg_color(i + 1),
                    elements=[
                        {"type": "animal", "value": animal, "color": self._bg_color(i + 3)},
                        {"type": "text", "value": animal.upper(), "color": "#FFFFFF"},
                        {"type": "sound_bubble", "value": sound, "color": "#FFDD44"},
                    ],
                    transition="fade",
                )
            )
            scene_num += 1

        # Outro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=7.0,
                narration_text=(
                    "Great job! You met all the animals! See you next time!"
                ),
                visual_description=(
                    "A joyful 3D animated scene with all the adorable cartoon "
                    "animals gathered together in a colorful meadow, waving "
                    "and celebrating, bright sunshine, Pixar-style render"
                ),
                background_color=self._bg_color(2),
                elements=[
                    {"type": "text", "value": "Great Job!", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # LULLABY script generator
    # ------------------------------------------------------------------

    def _generate_lullaby_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for a lullaby video.

        Lullabies are longer (target ~10 minutes for watch-time) so
        verses are repeated to fill the target duration.  Uses dark,
        soothing background colors and longer per-scene durations.

        Structure:
            Verse scenes repeated until the target duration is reached.
        """
        details = plan.topic_details
        song_name: str = details.get("name", "Twinkle Twinkle Little Star")
        target_duration: int = plan.target_duration_seconds

        verses = LULLABY_LYRICS.get(song_name)
        if verses is None:
            # Fallback to Twinkle Twinkle if the song name is unrecognized
            verses = LULLABY_LYRICS["Twinkle Twinkle Little Star"]
            song_name = "Twinkle Twinkle Little Star"

        scene_duration = 12.0  # seconds per verse scene
        scenes: list[ScriptScene] = []
        scene_num = 1
        elapsed = 0.0

        # Visual descriptions cycle for variety
        lullaby_visuals = [
            f"Soft starfield with gently twinkling stars. '{song_name}' text fades in.",
            "A crescent moon glows softly amid floating clouds.",
            "Gentle waves of color drift slowly across the screen.",
            "Soft bokeh lights rise slowly like fireflies.",
            "A calm night sky with shooting stars drifting by.",
            "Silhouette of a sleeping baby under soft moonlight.",
        ]

        # Repeat verses to fill the target duration
        verse_index = 0
        while elapsed < target_duration:
            verse = verses[verse_index % len(verses)]
            bg = LULLABY_BACKGROUNDS[scene_num % len(LULLABY_BACKGROUNDS)]
            visual = lullaby_visuals[(scene_num - 1) % len(lullaby_visuals)]

            # Use a slightly longer duration for later repetitions to
            # create a slowing, more soothing rhythm
            current_duration = scene_duration if scene_num <= len(verses) else 10.0

            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=current_duration,
                    narration_text=verse,
                    visual_description=visual,
                    background_color=bg,
                    elements=[
                        {"type": "text", "value": verse.split("\n")[0], "color": "#CCCCFF"},
                    ],
                    transition="fade",
                )
            )

            elapsed += current_duration
            scene_num += 1
            verse_index += 1

        return scenes

    # ------------------------------------------------------------------
    # NURSERY_RHYME script generator
    # ------------------------------------------------------------------

    def _generate_nursery_rhyme_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for a nursery rhyme video.

        Structure:
            1. Intro scene with the rhyme title
            2. One scene per verse of the rhyme
            3. Outro scene
        """
        details = plan.topic_details
        song_name: str = details.get("name", "Mary Had a Little Lamb")

        verses = NURSERY_LYRICS.get(song_name)
        if verses is None:
            # Fallback to Mary Had a Little Lamb
            verses = NURSERY_LYRICS["Mary Had a Little Lamb"]
            song_name = "Mary Had a Little Lamb"

        scenes: list[ScriptScene] = []
        scene_num = 1

        # Intro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text=f"Let's sing {song_name}! Sing along with me!",
                visual_description=(
                    f"A cheerful 3D animated storybook opening scene with "
                    f"golden musical notes floating around, colorful stage "
                    f"curtains, bright whimsical fairy-tale atmosphere"
                ),
                background_color=self._bg_color(0),
                elements=[
                    {"type": "text", "value": song_name, "color": "#FFFFFF"},
                    {"type": "decoration", "value": "musical_notes", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # Verse scenes
        for i, verse in enumerate(verses):
            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=8.0,
                    narration_text=verse,
                    visual_description=(
                        f"A cute 3D animated storybook scene illustrating: "
                        f"'{verse.split(chr(10))[0]}', adorable cartoon "
                        f"characters acting out the lyrics, bright colorful "
                        f"fairy-tale background, whimsical atmosphere"
                    ),
                    background_color=self._bg_color(i + 1),
                    elements=[
                        {"type": "lyrics", "value": verse, "color": "#FFFFFF"},
                    ],
                    transition="fade",
                )
            )
            scene_num += 1

        # Outro
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=7.0,
                narration_text="Great job singing along! See you next time!",
                visual_description=(
                    "A joyful 3D animated farewell scene with adorable "
                    "cartoon characters waving goodbye, golden musical notes "
                    "and colorful confetti, bright celebration atmosphere"
                ),
                background_color=self._bg_color(3),
                elements=[
                    {"type": "text", "value": "Great Job!", "color": "#FFD700"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # ANIME_DANCE script generator
    # ------------------------------------------------------------------

    def _generate_anime_dance_script(self, plan: ContentPlan) -> list[ScriptScene]:
        """Generate scenes for an anime hip-hop dance video.

        Structure:
            1. Establishing shot of the neon Tokyo setting
            2. Character introduction on the balcony/location
            3. Dance sequence scenes (one per pose/beat)
            4. Climactic final pose with full neon cityscape
            5. Outro/fade-out
        """
        details = plan.topic_details
        setting: str = details.get("setting", "tokyo_balcony")
        num_dance_scenes: int = details.get("num_dance_scenes", 8)

        setting_desc = SETTING_VISUALS.get(setting, SETTING_VISUALS["tokyo_balcony"])

        scenes: list[ScriptScene] = []
        scene_num = 1

        # --- Scene 1: Establishing shot ---
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=8.0,
                narration_text="",
                visual_description=(
                    f"Wide establishing shot. {setting_desc} "
                    "Cinematic camera slowly pans across the skyline. "
                    "Neon signs flicker to life one by one."
                ),
                background_color=NEON_BACKGROUNDS[0],
                elements=[
                    {"type": "neon_cityscape", "value": setting, "color": NEON_ACCENTS[0]},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # --- Scene 2: Character introduction ---
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text="",
                visual_description=(
                    "A stylish anime character steps into frame on the balcony. "
                    "They wear a loose bomber jacket, baggy pants, and a cap. "
                    "Wind catches their hair and jacket edges. "
                    "The city hums with neon glow behind them."
                ),
                background_color=NEON_BACKGROUNDS[1],
                elements=[
                    {"type": "neon_cityscape", "value": setting, "color": NEON_ACCENTS[1]},
                    {"type": "dancer_silhouette", "value": "intro_stance", "color": "#FFFFFF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # --- Dance sequence scenes ---
        poses = DANCE_POSES[:num_dance_scenes]
        for i, pose_data in enumerate(poses):
            accent = NEON_ACCENTS[i % len(NEON_ACCENTS)]
            bg = NEON_BACKGROUNDS[(i + 2) % len(NEON_BACKGROUNDS)]

            # Camera direction varies per scene for cinematic feel
            camera_directions = [
                "Camera slowly pans right, following the dancer's movement.",
                "Low-angle shot looking up at the dancer against the neon sky.",
                "Camera tracks in closer, neon reflections streaking across the lens.",
                "Wide shot pulls back to show the full cityscape framing the dancer.",
                "Dutch angle tilts as the beat drops, neon signs pulse brighter.",
                "Slow dolly-in focusing on the dancer's upper body and expression.",
                "Camera orbits slightly, catching different neon reflections.",
                "Bird's-eye pullback revealing the dancer on the balcony amidst the city.",
                "Tight medium shot, city bokeh blurring beautifully in the background.",
                "Final wide shot, every neon sign blazing at full intensity.",
            ]
            camera = camera_directions[i % len(camera_directions)]

            scenes.append(
                ScriptScene(
                    scene_number=scene_num,
                    duration_seconds=6.0,
                    narration_text="",
                    visual_description=(
                        f"Dance beat {i + 1}: {pose_data['desc']}. "
                        f"{camera} "
                        f"Neon {accent} light casts colored reflections on the floor "
                        "and the dancer's clothing. Secondary animation on hair and "
                        "jacket fabric shows natural weight and momentum."
                    ),
                    background_color=bg,
                    elements=[
                        {"type": "neon_cityscape", "value": setting, "color": accent},
                        {"type": "dancer_silhouette", "value": pose_data["pose"], "color": accent},
                        {"type": "neon_reflection", "value": "floor", "color": accent},
                    ],
                    transition="cut" if i % 3 == 2 else "fade",
                )
            )
            scene_num += 1

        # --- Climax: Final pose ---
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=8.0,
                narration_text="",
                visual_description=(
                    "The dancer hits a powerful final pose - one hand pointed "
                    "at the sky, weight anchored. Every neon sign in the Tokyo "
                    "skyline blazes at maximum brightness. A slow-motion wind "
                    "catches the jacket and hair. Camera pulls back into a "
                    "wide cinematic shot of the full city panorama."
                ),
                background_color=NEON_BACKGROUNDS[0],
                elements=[
                    {"type": "neon_cityscape", "value": setting, "color": "#FF00FF"},
                    {"type": "dancer_silhouette", "value": "final_pose", "color": "#00FFFF"},
                    {"type": "neon_reflection", "value": "full_bloom", "color": "#FF00FF"},
                ],
                transition="fade",
            )
        )
        scene_num += 1

        # --- Outro: Fade to city lights ---
        scenes.append(
            ScriptScene(
                scene_number=scene_num,
                duration_seconds=6.0,
                narration_text="",
                visual_description=(
                    "The dancer's silhouette slowly fades as the camera "
                    "drifts upward into the night sky. City lights twinkle "
                    "below like earthbound stars. The neon glow softens."
                ),
                background_color="#050510",
                elements=[
                    {"type": "neon_cityscape", "value": "distant", "color": "#7B68EE"},
                ],
                transition="fade",
            )
        )

        return scenes

    # ------------------------------------------------------------------
    # Checkpoint validation
    # ------------------------------------------------------------------

    def _validate_checkpoint(self, data: dict) -> bool:
        """Validate that checkpoint data contains a script."""
        return data.get("script") is not None
