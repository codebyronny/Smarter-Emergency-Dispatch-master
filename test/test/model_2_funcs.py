"""
model_2_funcs.py - Ambulance placement optimization (Model 2)

Modernized for Python 3.13 / geopandas 1.x / shapely 2.x:
  - Replaced geopandas.geoseries.GeoSeries/Point with shapely.geometry.Point + geopandas.GeoSeries
  - Removed deprecated geopandas.geoseries.GeoSeries constructor usage
  - pandas DataFrame.append() removed in pandas 2.0 - replaced with pd.concat
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import itertools
import math
import geopandas
from shapely.geometry import Point
from datetime import datetime
from sklearn.cluster import KMeans


def create_shapes_df(shape_file_path, shape_region_id_col='ZCTA5CE10'):
    """
    Loads and formats the shape file for our regions.

    INPUT: Path to a shape file with the shape for each region in a 'geometry' field.
           Name of the column containing region IDs.

    OUTPUT: A geopandas dataframe with each row a region, its shape polygon,
            and the shape's area and centroid.
    """
    gdf = geopandas.read_file(shape_file_path)
    gdf['area'] = gdf.geometry.area
    gdf['centroid'] = gdf.geometry.centroid
    gdf.rename(columns={shape_region_id_col: 'region_id'}, inplace=True)
    gdf.region_id = gdf.region_id.astype(str)
    gdf.set_index('region_id', inplace=True)
    gdf = gdf[['geometry', 'area', 'centroid']]
    return gdf


def get_region_points(region_shape, region_prediction, density_factor=100):
    """
    Calculates set of points per region based on given density factor.

    INPUT: geopandas polygon shape; prediction value for that shape; and the density factor,
           which is defined as the number of points in a region with area 0.0001 units squared.

    OUTPUT: Geopandas GeoSeries of uniformly distributed points within the shape.
    """
    base_density = density_factor / 0.0001
    density = base_density * region_prediction
    points_per_unit = math.sqrt(density)
    step_size = 1 / points_per_unit

    x1, y1, x2, y2 = region_shape.bounds
    x = np.arange(x1, x2 + step_size, step=step_size)
    y = np.arange(y1, y2 + step_size, step=step_size)

    # Modern shapely/geopandas: use shapely.geometry.Point directly
    box_points = geopandas.GeoSeries([Point(point) for point in itertools.product(x, y)])
    poly_points = box_points[box_points.within(region_shape)]

    return poly_points


def create_regions_df(shape_file_path, predictions_file_path, shape_region_id_col='ZCTA5CE10'):
    """
    Creates a single dataframe with shape information and the current prediction for each region.
    """
    shapes_df = create_shapes_df(shape_file_path, shape_region_id_col)

    predictions_df = predictions_file_path
    predictions_df['region_id'] = predictions_df.zcta.astype(str)
    predictions_df.set_index('region_id', inplace=True)

    regions_df = shapes_df.join(predictions_df)
    return regions_df


def create_points_df(regions_df):
    """
    Generates a dataframe of points labelled by the region that contains them.
    The density of points in each region is proportional to the prediction value.
    """
    df_list = []

    for region_id in regions_df.index:
        temp_region = regions_df.loc[region_id].copy()
        temp_points = get_region_points(temp_region.geometry, temp_region.call_counts, density_factor=50)
        temp_df = pd.DataFrame(temp_points, columns=['geometry'])
        temp_df['region_id'] = temp_region.name
        df_list.append(temp_df)

    # pd.DataFrame.append() removed in pandas 2.0 - use pd.concat
    points_df = geopandas.GeoDataFrame(pd.concat(df_list, ignore_index=True))
    points_df.reset_index(drop=True, inplace=True)
    points_df['lon_lat'] = points_df.geometry.apply(lambda p: (p.x, p.y))

    return points_df


def train_kmeans(ambulance_num, points_df):
    """
    Performs K-means clustering on the points dataframe.

    OUTPUT: A trained K-means model, where cluster centers are optimal ambulance locations.
    """
    train_data = np.array(list(points_df.lon_lat))
    kmeans = KMeans(n_clusters=ambulance_num, n_init=10).fit(train_data)
    return kmeans


def plot_model_2(points_df, regions_df, kmeans_model):
    """
    Creates a plot of all regions and their density-dependent points.
    """
    points_df['cluster'] = kmeans_model.labels_

    fig, ax = plt.subplots(1, figsize=(15, 15))
    points_df.plot(ax=ax, column='cluster')
    regions_df.geometry.boundary.plot(ax=ax, color='#ff33ff', linewidth=2)
    plt.plot(
        *zip(*kmeans_model.cluster_centers_),
        marker='*', markersize=14, color='#ff1a1a', ls=''
    )
    plt.plot()


def run_optimal_placement_model(
    shape_file_path, predictions_file_path, ambulance_num,
    results_file_path=None, shape_region_id_col='ZCTA5CE10'
):
    """
    Runs the full model for determining optimal staging locations for ambulances.

    OUTPUT: numpy array of ambulance placements; regions_df; points_df; trained K-means model.
    """
    regions_df = create_regions_df(shape_file_path, predictions_file_path, shape_region_id_col)
    points_df = create_points_df(regions_df)
    kmeans_model = train_kmeans(ambulance_num, points_df)
    placement_locations = kmeans_model.cluster_centers_

    if results_file_path:
        centers_df = pd.DataFrame(placement_locations, columns=['lon', 'lat'])
        centers_df.to_csv(results_file_path, index=False)

    return placement_locations, regions_df, points_df, kmeans_model


def update_ambulance_assignments(
    amb_status_file_path, shape_file_path, predictions_file_path,
    results_file_path=None, shape_region_id_col='ZCTA5CE10'
):
    """
    Wraps everything for model 2, including reassigning active ambulances to new placements.

    INPUT: A dataframe (or csv path) with current ambulance statuses and fields
           AMB_ID, LAT, LONG, AVAILABLE.

    OUTPUT: Updated dataframe of current ambulance statuses with new LAT/LONG for active units.
    """
    amb_locations = amb_status_file_path
    amb_locations = geopandas.GeoDataFrame(amb_locations)
    amb_locations = amb_locations.set_index('amb_id')

    active_locations = amb_locations[amb_locations.AVAILABLE == 1].copy()
    active_locations['location'] = active_locations.apply(
        lambda row: Point(row.LONG, row.LAT), axis=1
    )
    active_locations = active_locations['location']

    active_units = list(active_locations.index)
    amb_count = len(active_units)

    new_placement_locations, new_regions_df, new_points_df, new_kmeans_model = run_optimal_placement_model(
        shape_file_path=shape_file_path,
        predictions_file_path=predictions_file_path,
        ambulance_num=amb_count,
        results_file_path=results_file_path,
        shape_region_id_col=shape_region_id_col
    )

    # Convert cluster centers to shapely Points via GeoSeries
    new_locations = geopandas.GeoSeries([Point(point) for point in new_placement_locations])

    # Pairwise distances
    dist_arr = np.zeros(shape=(amb_count, amb_count))
    for amb_index in range(amb_count):
        for target_index in range(amb_count):
            dist_arr[amb_index, target_index] = (
                active_locations.tolist()[amb_index].distance(new_locations[target_index])
            )

    # Greedy nearest-pair assignment
    new_assignments = [0] * amb_count
    new_assignments_distances = [0] * amb_count
    max_val = dist_arr.max() + 1

    for i in range(amb_count):
        best_amb_index, best_target_index = np.unravel_index(dist_arr.argmin(), dist_arr.shape)
        new_assignments[best_amb_index] = new_locations[best_target_index]
        new_assignments_distances[best_amb_index] = dist_arr[best_amb_index, best_target_index]
        dist_arr[best_amb_index, :] = max_val
        dist_arr[:, best_target_index] = max_val

    for i in range(amb_count):
        amb_id = active_units[i]
        amb_locations.loc[amb_id, 'LONG'] = new_locations[i].x
        amb_locations.loc[amb_id, 'LAT'] = new_locations[i].y

    return amb_locations
