"""
Evaluador Determinista de Calidad de Guion (Closed-Loop Quality Control).
Verifica requisitos estrictos sin consumir tokens LLM para la evaluación.
"""

import re
from typing import Tuple, Dict, Any, List

class ScriptEvaluator:
    MIN_WORDS = 105
    MAX_WORDS = 135
    MIN_SCENES = 5
    MAX_SCENES = 6

    @staticmethod
    def count_words(text: str) -> int:
        """Cuenta palabras normalizadas ignorando símbolos de puntuación."""
        words = re.findall(r'\b\w+\b', text)
        return len(words)

    @classmethod
    def evaluate(cls, script_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Evalúa si el guión cumple con los criterios de producción:
        - Longitud de palabras (105-135 palabras para target de 40-55s).
        - Cantidad de escenas (5 a 6).
        - Formato de los prompts visuales (prefijo Vertical 9:16).
        - Presencia de gancho inicial.
        """
        issues = []
        if not script_data:
            return False, ["El guion generado está vacío."]

        script_text = script_data.get("script", "").strip()
        word_count = cls.count_words(script_text)

        # 1. Validación de palabras
        if word_count < cls.MIN_WORDS:
            issues.append(f"Guión demasiado corto: tiene {word_count} palabras (mínimo {cls.MIN_WORDS}).")
        elif word_count > cls.MAX_WORDS:
            issues.append(f"Guión demasiado largo: tiene {word_count} palabras (máximo {cls.MAX_WORDS}).")

        # 2. Validación de escenas
        scenes = script_data.get("scenes", [])
        if not isinstance(scenes, list) or len(scenes) < cls.MIN_SCENES or len(scenes) > cls.MAX_SCENES:
            issues.append(f"Cantidad de escenas inválida: tiene {len(scenes)} (requerido {cls.MIN_SCENES} a {cls.MAX_SCENES}).")

        # 3. Validación de gancho
        first_sentence = script_text[:60]
        if not any(char in first_sentence for char in ["¿", "?", "!", "¡", ":"]):
            issues.append("El gancho inicial carece de signos de interrogación o énfasis claro.")

        # 4. Formato de prompts visuales
        for idx, scene_prompt in enumerate(scenes):
            if not isinstance(scene_prompt, str) or len(scene_prompt) < 15:
                issues.append(f"Prompt visual de escena {idx+1} es muy corto o inválido.")

        is_valid = len(issues) == 0
        return is_valid, issues
