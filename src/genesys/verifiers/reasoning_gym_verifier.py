from reasoning_gym.factory import create_dataset

from genesys.schemas import Response
from genesys.verifiers.base_verifier import BaseVerifier


class ReasoningGymVerifier(BaseVerifier):

    def __init__(self):
        # TODO: init all datasets
        pass

    def verify(self, result: Response):
        """
        Required: this example verify function checks the length of the llm response
        and rewards responses over a threshold specified in the dataset.

        The output should be a dict with a score from 0-1 and a 'verification_result_info' dict containing metadata
        """

        # Example: Instantiate a dataset using its registered name
        dataset_name = result["source"]
        entry = {"answer": result["verification_info"]["ground_truth"], "metadata": result["metadata"]}
        config_kwargs = {
            "size": 1,  # Example configuration, replace with actual configuration parameters
        }

        rg_ds = create_dataset(name=dataset_name, **config_kwargs)
        score = rg_ds.score_answer(answer=result["llm_response"], entry=entry)
        return dict(score=score, verification_result_info={})