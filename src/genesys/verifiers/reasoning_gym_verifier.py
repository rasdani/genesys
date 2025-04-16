from reasoning_gym.factory import DATASETS, create_dataset

from genesys.schemas import Response
from genesys.verifiers.base_verifier import BaseVerifier


class ReasoningGymVerifier(BaseVerifier):
    """
    Verifier for procedural datasets from reasoning gym.
    https://github.com/open-thought/reasoning-gym
    """

    def __init__(self):
        del DATASETS["composite"]
        self.score_answer_fns = {
            dataset_name: create_dataset(name=dataset_name, size=1).score_answer for dataset_name in DATASETS.keys()
        }

    def verify(self, result: Response):
        """
        Evaluates the answer with the scoring function from the corresponding reasoning gym dataset.

        The score is a float between 0 and 1.
        """

        dataset_name = result["source"]
        entry = {"answer": result["verification_info"]["ground_truth"], "metadata": result["metadata"]}

        score = self.score_answer_fns[dataset_name](answer=result["llm_response"], entry=entry)
        return dict(score=score, verification_result_info={})
