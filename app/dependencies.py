"""
FastAPI dependencies for the vLLM Router application.
"""
from .config import get_config as get_global_config, Config
from .load_balancer import get_load_balancer as get_global_load_balancer, LoadBalancer

def get_config() -> Config:
    """
    Dependency function to get the global configuration instance.
    """
    return get_global_config()

def get_load_balancer() -> LoadBalancer:
    """
    Dependency function to get the global load balancer instance.
    """
    return get_global_load_balancer()
