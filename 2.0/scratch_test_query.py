import sys
from assistant import CollegeAssistant

class DummyUser:
    id = 1

def main():
    assistant = CollegeAssistant()
    assistant.setup()
    
    question = "which lecture is from 8 am to 9 am on monday in BTI Div. D timetable ?"
    print(f"\n--- QUERY: {question} ---")
    
    result = assistant.ask(question, user=DummyUser())
    
    with open("test_output.txt", "w", encoding="utf-8") as f:
        f.write("--- RAW CHUNKS TEXT ---\n")
        for i, c in enumerate(result['chunks']):
            f.write(f"\nChunk {i} (Score: {c.get('score')}):\n")
            f.write(c.get('text') + "\n")
            f.write("-" * 40 + "\n")
            
        f.write("\n--- PROMPT GENERATED ---\n")
        prompt = assistant.generator.build_prompt(question, result['chunks'], history=[])
        f.write(prompt + "\n")

if __name__ == "__main__":
    main()
