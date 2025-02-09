#!/home/sohfix/PycharmProjects/rehab/renv/bin/python3

import random
import sys
import time
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich.prompt import Prompt, IntPrompt
from rich import print

console = Console()

# 100 Taylor Swift fan facts
swift_facts = [
    {"factNumber": 1, "fact": "Taylor Alison Swift was born on December 13, 1989, in Reading, Pennsylvania."},
    {"factNumber": 2, "fact": "She was named after singer-songwriter James Taylor."},
    {"factNumber": 3, "fact": "She spent her early years living on a Christmas tree farm."},
    {"factNumber": 4, "fact": "She wrote her first song, \"Lucky You,\" at the age of 12."},
    {"factNumber": 5, "fact": "She moved to Nashville at 14 to pursue a music career."},
    {"factNumber": 6, "fact": "She signed with Big Machine Records as their first signed artist."},
    {"factNumber": 7, "fact": "Her debut single, \"Tim McGraw,\" was released on June 19, 2006."},
    {"factNumber": 8, "fact": "Her self-titled debut album, \"Taylor Swift,\" was released in 2006."},
    {"factNumber": 9, "fact": "Her second album, \"Fearless,\" came out in 2008."},
    {"factNumber": 10,
     "fact": "\"Fearless\" won Album of the Year at the 2010 Grammy Awards, making her the youngest artist to win that award at that time."},
    {"factNumber": 11, "fact": "She wrote or co-wrote every track on her album \"Speak Now\" (2010)."},
    {"factNumber": 12, "fact": "\"Speak Now\" was officially announced during a live stream in July 2010."},
    {"factNumber": 13, "fact": "She is known for her storytelling songwriting, often drawn from personal experiences."},
    {"factNumber": 14, "fact": "Her dedicated fan base is known as \"Swifties.\""},
    {"factNumber": 15, "fact": "She often incorporates the number 13, referring to it as her lucky number."},
    {"factNumber": 16,
     "fact": "She was the first country artist to win an MTV Video Music Award, for \"You Belong with Me\" (2009)."},
    {"factNumber": 17, "fact": "Kanye West famously interrupted her acceptance speech at the 2009 VMAs."},
    {"factNumber": 18, "fact": "\"Red\" (2012) was notable for mixing country and pop influences."},
    {"factNumber": 19, "fact": "\"1989\" (2014) was her official transition into pop music."},
    {"factNumber": 20,
     "fact": "\"1989\" won Album of the Year at the 2016 Grammys, making her the first woman to win the top Grammy twice for her own albums."},
    {"factNumber": 21, "fact": "She has a cat named Meredith Grey, named after the \"Grey's Anatomy\" character."},
    {"factNumber": 22, "fact": "She has a cat named Olivia Benson, inspired by the \"Law & Order: SVU\" character."},
    {"factNumber": 23, "fact": "She has another cat named Benjamin Button, introduced during her \"ME!\" era."},
    {"factNumber": 24, "fact": "She has been listed in Time's 100 Most Influential People multiple times."},
    {"factNumber": 25, "fact": "She provided the voice of Audrey in the animated film \"The Lorax\" (2012)."},
    {"factNumber": 26, "fact": "She made a cameo as Felicia in the movie \"Valentine's Day\" (2010)."},
    {"factNumber": 27,
     "fact": "She co-wrote Calvin Harris and Rihanna’s hit \"This Is What You Came For\" under the pseudonym Nils Sjöberg."},
    {"factNumber": 28,
     "fact": "Her 2017 album \"Reputation\" was heavily influenced by media scrutiny and privacy concerns."},
    {"factNumber": 29, "fact": "\"Look What You Made Me Do\" was the lead single from \"Reputation.\""},
    {"factNumber": 30, "fact": "Her \"Reputation Stadium Tour\" became one of the highest-grossing tours of all time."},
    {"factNumber": 31, "fact": "She left Big Machine Records in 2018 and signed with Republic Records/UMG."},
    {"factNumber": 32, "fact": "Her seventh studio album, \"Lover,\" was released in 2019."},
    {"factNumber": 33, "fact": "\"Lover\" was her first album fully owned by her under her new record deal."},
    {"factNumber": 34,
     "fact": "She had a public dispute over her master recordings with music executive Scooter Braun."},
    {"factNumber": 35,
     "fact": "She announced she would re-record her first six albums to gain control over her masters."},
    {"factNumber": 36,
     "fact": "The first re-recorded album she released was \"Fearless (Taylor's Version)\" in April 2021."},
    {"factNumber": 37, "fact": "\"Red (Taylor's Version)\" followed in November 2021."},
    {"factNumber": 38, "fact": "The 10-minute version of \"All Too Well\" garnered widespread critical acclaim."},
    {"factNumber": 39,
     "fact": "She wrote and directed the short film for \"All Too Well\" starring Sadie Sink and Dylan O'Brien."},
    {"factNumber": 40,
     "fact": "She created two albums during the pandemic: \"Folklore\" and \"Evermore\" (both in 2020)."},
    {"factNumber": 41, "fact": "\"Folklore\" was a surprise release in July 2020."},
    {"factNumber": 42, "fact": "\"Folklore\" won Album of the Year at the 2021 Grammys."},
    {"factNumber": 43, "fact": "\"Evermore\" was released in December 2020, just five months after \"Folklore.\""},
    {"factNumber": 44,
     "fact": "She collaborated with Aaron Dessner (The National) and Jack Antonoff on both \"Folklore\" and \"Evermore.\""},
    {"factNumber": 45, "fact": "She teamed up with Bon Iver on the track \"exile\" from \"Folklore.\""},
    {"factNumber": 46, "fact": "\"Coney Island\" on \"Evermore\" features The National."},
    {"factNumber": 47,
     "fact": "She set a record for most simultaneous U.S. Hot 100 entries by a female artist when \"Folklore\" was released."},
    {"factNumber": 48,
     "fact": "She co-wrote the original song \"Beautiful Ghosts\" for the film adaptation of \"Cats\" (2019)."},
    {"factNumber": 49,
     "fact": "She has won numerous American Music Awards, Billboard Music Awards, and Country Music Association Awards."},
    {"factNumber": 50, "fact": "She appeared as a \"Mega Mentor\" on the TV singing competition \"The Voice.\""},
    {"factNumber": 51, "fact": "She is known for surprising fans with personal gifts, an act called \"Swiftmas.\""},
    {"factNumber": 52, "fact": "Her album liner notes famously contained hidden messages related to each track."},
    {"factNumber": 53, "fact": "She has a younger brother named Austin, who is an actor."},
    {"factNumber": 54, "fact": "Taylor Swift is approximately 5 feet 10 inches tall (178 cm)."},
    {"factNumber": 55, "fact": "She once lived in the same New York apartment building as Orlando Bloom."},
    {"factNumber": 56,
     "fact": "She has been recognized for various philanthropic efforts, including disaster relief and education."},
    {"factNumber": 57,
     "fact": "She donated $4 million to the Country Music Hall of Fame to fund a music education center."},
    {"factNumber": 58, "fact": "At one time, she was recognized as the top-selling digital artist in music history."},
    {"factNumber": 59,
     "fact": "Her \"Bad Blood\" music video featured cameo appearances by Selena Gomez, Karlie Kloss, and more."},
    {"factNumber": 60, "fact": "\"Shake It Off\" was the lead single from her album \"1989.\""},
    {"factNumber": 61, "fact": "The \"Blank Space\" video cleverly satirizes media portrayals of her dating life."},
    {"factNumber": 62, "fact": "She made cameo appearances on \"CSI\" and \"New Girl.\""},
    {"factNumber": 63,
     "fact": "She was repeatedly honored as Songwriter/Artist of the Year by the Nashville Songwriters Association."},
    {"factNumber": 64, "fact": "She received the Pinnacle Award from the Country Music Association in 2013."},
    {"factNumber": 65,
     "fact": "She became the first woman to replace herself at No.1 on the Billboard Hot 100 with \"Blank Space\" following \"Shake It Off.\""},
    {"factNumber": 66, "fact": "Her birth year is referenced in the title of her album \"1989.\""},
    {"factNumber": 67,
     "fact": "She holds \"Secret Sessions\" where she invites select fans to her homes to preview albums before release."},
    {"factNumber": 68, "fact": "She has sold over 200 million records worldwide."},
    {"factNumber": 69, "fact": "She received an honorary Doctor of Fine Arts degree from New York University in 2022."},
    {"factNumber": 70,
     "fact": "She wrote \"Better Man,\" performed by Little Big Town, which won a CMA Award for Song of the Year in 2017."},
    {"factNumber": 71, "fact": "She has frequently appeared on Forbes' list of highest-paid women in music."},
    {"factNumber": 72,
     "fact": "She was the first female solo artist to win two MTV Video Music Awards for Video of the Year (\"You Belong with Me\" and \"Blank Space\")."},
    {"factNumber": 73, "fact": "She performed the national anthem at a Philadelphia 76ers game at age 11."},
    {"factNumber": 74, "fact": "She has performed during the Victoria's Secret Fashion Show."},
    {"factNumber": 75, "fact": "She was named Billboard’s Woman of the Year in both 2011 and 2014."},
    {"factNumber": 76,
     "fact": "She performed at the White House for the Obamas during a Fourth of July event in 2010."},
    {"factNumber": 77, "fact": "\"ME!\" (featuring Brendon Urie) was the lead single from her album \"Lover.\""},
    {"factNumber": 78,
     "fact": "The \"ME!\" music video broke the record for the highest 24-hour debut by a solo or female artist on YouTube."},
    {"factNumber": 79,
     "fact": "She wrote \"You'll Always Find Your Way Back Home\" for Miley Cyrus in \"Hannah Montana: The Movie.\""},
    {"factNumber": 80, "fact": "She was both host and musical guest on \"Saturday Night Live\" in November 2009."},
    {"factNumber": 81,
     "fact": "She and Ed Sheeran collaborated on tracks like \"Everything Has Changed\" and \"End Game.\""},
    {"factNumber": 82, "fact": "She was inspired early on by country stars like Shania Twain and Faith Hill."},
    {"factNumber": 83, "fact": "She has cited Paul McCartney as a key influence on her songwriting."},
    {"factNumber": 84, "fact": "She was named Artist of the Decade at the 2019 American Music Awards."},
    {"factNumber": 85, "fact": "She is known for evolving her style and aesthetic with each new \"era.\""},
    {"factNumber": 86, "fact": "Her tenth studio album, \"Midnights,\" was released in October 2022."},
    {"factNumber": 87, "fact": "\"Midnights\" broke the Spotify record for most-streamed album in a single day."},
    {"factNumber": 88,
     "fact": "She became the first artist to occupy the entire Top 10 on the Billboard Hot 100 with songs from \"Midnights.\""},
    {"factNumber": 89,
     "fact": "She collaborated with Phoebe Bridgers on \"Nothing New,\" released on \"Red (Taylor's Version).\""},
    {"factNumber": 90, "fact": "She wrote the song \"Carolina\" for the film \"Where the Crawdads Sing\" (2022)."},
    {"factNumber": 91,
     "fact": "She has supported numerous charities, focusing on arts education, literacy, and disaster relief."},
    {"factNumber": 92, "fact": "She launched a line of fragrances, starting with \"Wonderstruck\" in 2011."},
    {"factNumber": 93, "fact": "She had a cameo in the 2022 film \"Amsterdam.\""},
    {"factNumber": 94,
     "fact": "She is known for planting Easter eggs in her social media posts and music videos to hint at future projects."},
    {"factNumber": 95,
     "fact": "She has been a vocal advocate for fair compensation for artists on streaming services."},
    {"factNumber": 96, "fact": "She was honored with the iHeartRadio Innovator Award in 2023."},
    {"factNumber": 97, "fact": "She has won multiple BRIT Awards for International Female Solo Artist."},
    {"factNumber": 98, "fact": "She collaborated with HAIM on the track \"No Body, No Crime\" from \"Evermore.\""},
    {"factNumber": 99,
     "fact": "She has worked with prominent music video directors like Joseph Kahn, Roman White, and Blake Lively."},
    {"factNumber": 100,
     "fact": "She performed the full 10-minute version of \"All Too Well (Taylor's Version)\" on \"Saturday Night Live\" in November 2021."}
]

scoreboard = []  # to store tuples like (initials, score, total_questions)


def display_main_menu():
    console.print("\n[bold cyan]Welcome to the Swift App![/bold cyan]")
    console.print("1) Take the 100-Question Swift Quiz (or fewer if you like)")
    console.print("2) View Scoreboard")
    console.print("3) Quit\n")


def take_swift_quiz():
    """
    Presents a multiple-choice quiz based on the facts in swift_facts.
    User can choose how many questions (up to 100).
    At the end, we calculate how many were correct -> 'Swifty level'.
    Then prompts user for initials and stores result in scoreboard.
    """
    # Prompt how many questions to present
    num_questions = IntPrompt.ask(
        "[bold yellow]How many questions do you want? (max 100)[/bold yellow]",
        default=10
    )
    if num_questions < 1:
        console.print("[red]Invalid number of questions. Returning to main menu.[/red]")
        return

    if num_questions > 100:
        console.print("[red]Can't exceed 100. Using 100 questions.[/red]")
        num_questions = 100

    # Randomly select the needed number of facts
    quiz_facts = random.sample(swift_facts, k=num_questions)

    # We'll track correct answers
    correct_answers = 0

    console.print("\n[bold magenta]Starting the quiz...[/bold magenta]")
    # Show a tiny progress bar "Loading" for aesthetics
    for _ in track(range(10), description="Preparing..."):
        time.sleep(0.03)

    # For each selected fact, make a question
    for i, correct_fact in enumerate(quiz_facts, start=1):
        console.print(f"\n[bold cyan]Question {i} of {num_questions}[/bold cyan]")

        # The correct statement:
        statement_correct = correct_fact["fact"]

        # Get 3 random distractors from the other facts
        other_facts = [f["fact"] for f in swift_facts if f != correct_fact]
        distractors = random.sample(other_facts, 3)

        # Combine correct statement + distractors
        options = [statement_correct] + distractors
        random.shuffle(options)

        # Display multiple choice (A, B, C, D)
        letters = ["A", "B", "C", "D"]
        for letter, opt in zip(letters, options):
            console.print(f"[bold]{letter}.[/bold] {opt}")

        # Prompt user for answer
        user_answer = Prompt.ask(
            "[bold white]Choose your answer (A/B/C/D)[/bold white]",
            choices=["A", "B", "C", "D"],
            default="A"
        )

        # Map user_answer to actual statement
        chosen_index = letters.index(user_answer)
        chosen_statement = options[chosen_index]

        # Check correctness
        if chosen_statement == statement_correct:
            correct_answers += 1
            console.print("[bold green]Correct![/bold green]")
        else:
            console.print("[bold red]Incorrect![/bold red]")
            console.print(f"[italic]The correct fact was: {statement_correct}[/italic]")

    # End of quiz: Show results
    console.print(f"\n[bold magenta]Quiz Completed![/bold magenta]")
    console.print(f"You got [bold]{correct_answers}[/bold] out of [bold]{num_questions}[/bold] correct.")

    # Calculate a "Swifty level" — just do correct count for now
    swifty_level = correct_answers

    # Prompt user to store initials
    console.print("\n[bold yellow]Enter your 3-character arcade initials:[/bold yellow]")
    initials = Prompt.ask("Initials").upper()
    initials = initials[:3]  # keep only first 3 chars

    scoreboard.append((initials, correct_answers, num_questions))
    console.print(f"\nSaved [bold]{initials}[/bold] with a score of {correct_answers}/{num_questions}!\n")


def view_scoreboard():
    """
    Display scoreboard with initials and quiz results in a table.
    Sort by highest raw score, then by number of questions descending.
    """
    if not scoreboard:
        console.print("[bold red]\nNo entries on the scoreboard yet![/bold red]")
        return

    # Sort primarily by number correct (descending), secondary by total questions (descending)
    sorted_scores = sorted(scoreboard, key=lambda x: (x[1], x[2]), reverse=True)

    table = Table(title="Swift Arcade Scoreboard", show_lines=True)
    table.add_column("Rank", justify="right", style="bold cyan")
    table.add_column("Initials", style="bold yellow")
    table.add_column("Score", justify="center", style="bold green")
    table.add_column("Out of", justify="center", style="bold white")

    for i, entry in enumerate(sorted_scores, start=1):
        initials, correct, total = entry
        table.add_row(str(i), initials, str(correct), str(total))

    console.print(table)


def main():
    while True:
        display_main_menu()
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3"])

        if choice == "1":
            take_swift_quiz()
        elif choice == "2":
            view_scoreboard()
        elif choice == "3":
            console.print("[bold cyan]\nThanks for using the Swift App! Goodbye.[/bold cyan]")
            sys.exit(0)


if __name__ == "__main__":
    main()
