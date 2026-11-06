"""Owns the pool/saver; never runs setup(), migrations, or memory fallback."""
import logging
from contextlib import asynccontextmanager
from app.adapters.patterns.decentralized import _build_decentralized_graph
from app.database.conversation_owners import ConversationOwnersRepository
from app.database.conversation_locks import ConversationLocks
logger = logging.getLogger(__name__)

def _checkpoint_resources(settings):
    from app.database.decentralized_checkpoint import build_checkpoint_resources
    return build_checkpoint_resources(settings)

def create_lifespan(*, graph_factories, checkpoint_resources_factory, financial_repository):
    @asynccontextmanager
    async def lifespan(application):
        resources = None
        try:
            if graph_factories is None:
                stage = "configuration"
                try:
                    if checkpoint_resources_factory is None:
                        from app.database.decentralized_checkpoint import load_checkpoint_settings
                        checkpoint_settings = load_checkpoint_settings()
                        stage = "pool_construction"
                        resources = _checkpoint_resources(checkpoint_settings)
                    else:
                        stage = "pool_construction"
                        resources = checkpoint_resources_factory()
                    stage = "pool_open"
                    resources.pool.open(wait=True)
                    stage = "graph_construction"
                    if financial_repository is None:
                        application.state.decentralized_graph = _build_decentralized_graph(resources.saver)
                    else:
                        application.state.decentralized_graph = _build_decentralized_graph(
                            resources.saver, financial_repository=financial_repository)
                    stage = "resource_association"
                    application.state.checkpoint_resources = resources
                    application.state.conversation_owners = ConversationOwnersRepository(resources.pool)
                    if resources.pool.max_size < 2:
                        raise RuntimeError("Pool requiere capacidad para coordinación y saver")
                    application.state.conversation_locks = ConversationLocks(resources.pool)
                except Exception as exc:
                    logger.error("Decentralized checkpoint initialization failed; stage=%s; type=%s",
                                 stage, type(exc).__name__)
                    if resources is not None:
                        try:
                            resources.close()
                        except Exception:
                            logger.error("Decentralized checkpoint cleanup failed")
                        resources = None
                    application.state.decentralized_graph = None
            yield
        finally:
            application.state.decentralized_graph = None
            application.state.checkpoint_resources = None
            application.state.conversation_owners = None
            application.state.conversation_locks = None
            if hasattr(application.state, "patterns"):
                application.state.patterns["decentralized"]._graph = None
            if resources is not None:
                try:
                    resources.close()
                except Exception:
                    logger.error("Decentralized checkpoint shutdown failed")
    return lifespan
