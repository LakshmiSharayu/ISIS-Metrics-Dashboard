"""
Dashboard module for creating interactive visualizations
"""

import logging
from datetime import datetime, timedelta
import pandas as pd
from database import get_metrics_history, get_latest_metrics

logger = logging.getLogger(__name__)


def create_dashboard_data(device: str, hours: int = 24) -> dict:
    """
    Prepare data for dashboard visualization
    
    Args:
        device: Device name
        hours: Hours of historical data to include
    
    Returns:
        Dictionary with metrics data for frontend
    """
    try:
        # Get historical data
        history = get_metrics_history(device, hours)
        
        if not history:
            return {
                'success': False,
                'message': 'No data available',
                'device': device
            }
        
        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Prepare time series data
        timeline = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()
        
        dashboard_data = {
            'success': True,
            'device': device,
            'update_time': datetime.utcnow().isoformat(),
            'current_metrics': {
                'total_lsps': int(df['total_lsps'].iloc[-1]) if len(df) > 0 else 0,
                'lsp_database_size': int(df['lsp_database_size'].iloc[-1]) if len(df) > 0 else 0,
                'isis_nodes': int(df['isis_nodes'].iloc[-1]) if len(df) > 0 else 0,
                'prefixes': int(df['prefixes'].iloc[-1]) if len(df) > 0 else 0,
                'lsp_count_l1': int(df['lsp_count_l1'].iloc[-1]) if len(df) > 0 else 0,
                'lsp_count_l2': int(df['lsp_count_l2'].iloc[-1]) if len(df) > 0 else 0,
                'adjacencies': int(df['adjacencies'].iloc[-1]) if len(df) > 0 else 0,
                'interfaces': int(df['interfaces'].iloc[-1]) if len(df) > 0 else 0,
                'database_overload': bool(df['database_overload'].iloc[-1]) if len(df) > 0 else False
            },
            'time_series': {
                'timestamp': timeline,
                'total_lsps': df['total_lsps'].tolist(),
                'lsp_database_size': df['lsp_database_size'].tolist(),
                'isis_nodes': df['isis_nodes'].tolist(),
                'lsp_count_l1': df['lsp_count_l1'].tolist(),
                'lsp_count_l2': df['lsp_count_l2'].tolist(),
                'adjacencies': df['adjacencies'].tolist()
            },
            'statistics': {
                'total_lsps_avg': float(df['total_lsps'].mean()),
                'total_lsps_max': int(df['total_lsps'].max()),
                'total_lsps_min': int(df['total_lsps'].min()),
                'lsp_database_size_avg': float(df['lsp_database_size'].mean()),
                'isis_nodes_avg': float(df['isis_nodes'].mean()),
                'isis_nodes_max': int(df['isis_nodes'].max())
            }
        }
        
        return dashboard_data
    
    except Exception as e:
        logger.error(f"Error creating dashboard data: {str(e)}")
        return {
            'success': False,
            'message': str(e),
            'device': device
        }


def create_dashboard_callbacks(app, isis_collector):
    """
    Create Flask route callbacks for dashboard updates
    
    Args:
        app: Flask application instance
        isis_collector: ISISCollector instance
    """
    @app.route('/api/dashboard/<device>')
    def get_dashboard(device):
        """Get dashboard data for a device"""
        from flask import jsonify, request
        hours = request.args.get('hours', 24, type=int)
        data = create_dashboard_data(device, hours)
        return jsonify(data)
    
    @app.route('/api/dashboard/<device>/stats')
    def get_dashboard_stats(device):
        """Get dashboard statistics for a device"""
        from flask import jsonify, request
        hours = request.args.get('hours', 24, type=int)
        
        try:
            history = get_metrics_history(device, hours)
            
            if not history:
                return jsonify({'error': 'No data available'}), 404
            
            df = pd.DataFrame(history)
            
            stats = {
                'device': device,
                'data_points': len(df),
                'total_lsps_avg': float(df['total_lsps'].mean()),
                'total_lsps_max': int(df['total_lsps'].max()),
                'total_lsps_min': int(df['total_lsps'].min()),
                'isis_nodes_avg': float(df['isis_nodes'].mean()),
                'isis_nodes_max': int(df['isis_nodes'].max()),
                'lsp_database_size_avg': float(df['lsp_database_size'].mean()),
                'adjacencies_avg': float(df['adjacencies'].mean()),
                'collection_period_hours': hours
            }
            
            return jsonify(stats)
        
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {str(e)}")
            return jsonify({'error': str(e)}), 500
