"""
Verification for Reflection Module

Verifies sub-goal accomplishment using screen question answering.
Checks if sub-goal success criteria are met.

TODO - Implementation Instructions:
    1. Define VerificationResult dataclass:
        - is_accomplished, confidence, reasoning, unmet_criteria
    2. Implement Verifier class:
        - Constructor takes config and gemini_client
        - Initialize logger
    3. Implement verify_subgoal(subgoal, gui_state) -> VerificationResult:
        - Create question from subgoal success criteria
        - Call gemini_client for screen QA
        - Parse response
        - Return VerificationResult
    4. Implement create_verification_prompt(subgoal, gui_state, screenshot) -> str:
        - Create a question asking if subgoal is accomplished
        - Include visual context
        - Ask for confidence score
        - Return prompt
    5. Implement parse_verification_response(response: str) -> tuple:
        - Extract Yes/No answer
        - Extract confidence
        - Extract reasoning
        - Return (is_accomplished, confidence, reasoning)
    6. Add logging
"""

from typing import Optional, List
from dataclasses import dataclass


@dataclass
class VerificationResult:
    """
    TODO - Implementation Instructions:
        1. Define fields: is_accomplished, confidence, reasoning, unmet_criteria
        2. Implement to_dict()
    """
    pass


class Verifier:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config, gemini_client):
            - Store config and gemini_client
            - Initialize logger
        2. Implement verify_subgoal(subgoal, gui_state) -> VerificationResult:
            - Create verification prompt
            - Call gemini_client.query_with_image()
            - Parse response
            - Return VerificationResult
        3. Implement create_verification_prompt(subgoal, gui_state) -> str:
            - Ask: "Has this sub-goal been accomplished: [description]?"
            - Include success criteria
            - Ask for confidence score
            - Return prompt string
        4. Implement parse_verification_response(response: str) -> VerificationResult:
            - Extract accomplished status
            - Extract confidence
            - Extract reasoning
            - Return VerificationResult
    """
    pass


def verify_subgoal_accomplishment(subgoal, gui_state, gemini_client) -> VerificationResult:
    """
    TODO - Implementation Instructions:
        1. Create Verifier instance
        2. Call verify_subgoal()
        3. Return VerificationResult
    """
    pass
