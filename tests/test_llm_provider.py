"""Tests for the shared model-provider factory (src/llm.py).

Every Settings(...) construction passes _env_file=None so these tests are
hermetic and don't pick up whatever a developer's local .env happens to
contain (e.g. real Azure credentials during a live validation run).
"""

import pytest
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings, ChatOpenAI, OpenAIEmbeddings

from src.config import Settings

OPENROUTER_SETTINGS_KWARGS = {
    "_env_file": None,
    "MODEL_PROVIDER": "openrouter",
    "OPENROUTER_API_KEY": "fake-openrouter-key",
    "OPENROUTER_MODEL_ID": "fake/model",
}

AZURE_SETTINGS_KWARGS = {
    "_env_file": None,
    "MODEL_PROVIDER": "azure_openai",
    "AZURE_OPENAI_API_KEY": "fake-key",
    "AZURE_OPENAI_ENDPOINT": "https://fake-resource.openai.azure.com/",
    "AZURE_OPENAI_API_VERSION": "2024-10-21",
    "AZURE_OPENAI_CHAT_DEPLOYMENT": "fake-chat-deployment",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "fake-embedding-deployment",
}


class TestOpenRouterProvider:
    def test_build_chat_model_returns_openrouter_client(self, monkeypatch):
        import src.llm as llm_module

        monkeypatch.setattr(llm_module, "settings", Settings(**OPENROUTER_SETTINGS_KWARGS))

        model = llm_module.build_chat_model()

        assert isinstance(model, ChatOpenAI)
        assert model.openai_api_base == "https://openrouter.ai/api/v1"

    def test_build_embeddings_model_returns_openrouter_client(self, monkeypatch):
        import src.llm as llm_module

        monkeypatch.setattr(llm_module, "settings", Settings(**OPENROUTER_SETTINGS_KWARGS))

        model = llm_module.build_embeddings_model()

        assert isinstance(model, OpenAIEmbeddings)
        assert model.openai_api_base == "https://openrouter.ai/api/v1"


class TestAzureOpenAIProvider:
    def test_build_chat_model_returns_azure_client(self, monkeypatch):
        import src.llm as llm_module

        monkeypatch.setattr(llm_module, "settings", Settings(**AZURE_SETTINGS_KWARGS))

        model = llm_module.build_chat_model()

        assert isinstance(model, AzureChatOpenAI)
        assert model.azure_endpoint == "https://fake-resource.openai.azure.com/"
        assert model.deployment_name == "fake-chat-deployment"
        assert model.openai_api_version == "2024-10-21"

    def test_build_embeddings_model_returns_azure_client(self, monkeypatch):
        import src.llm as llm_module

        monkeypatch.setattr(llm_module, "settings", Settings(**AZURE_SETTINGS_KWARGS))

        model = llm_module.build_embeddings_model()

        assert isinstance(model, AzureOpenAIEmbeddings)
        assert model.azure_endpoint == "https://fake-resource.openai.azure.com/"
        assert model.deployment == "fake-embedding-deployment"
        assert model.dimensions == 1536

    def test_missing_azure_fields_raise_at_settings_construction(self):
        with pytest.raises(ValueError, match="MODEL_PROVIDER=azure_openai requires"):
            Settings(_env_file=None, MODEL_PROVIDER="azure_openai")

    def test_error_names_the_missing_fields(self):
        with pytest.raises(ValueError, match="AZURE_OPENAI_CHAT_DEPLOYMENT"):
            Settings(
                _env_file=None,
                MODEL_PROVIDER="azure_openai",
                AZURE_OPENAI_API_KEY="fake-key",
                AZURE_OPENAI_ENDPOINT="https://fake-resource.openai.azure.com/",
                AZURE_OPENAI_EMBEDDING_DEPLOYMENT="fake-embedding-deployment",
            )
