package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

var ErrNotFound = errors.New("resource not found")

type APIClient struct {
	baseURL      string
	apiKey       string
	bearerToken  string
	httpClient   *http.Client
	pollInterval time.Duration
	pollTimeout  time.Duration
}

func NewAPIClient(
	baseURL string,
	apiKey string,
	bearerToken string,
	pollIntervalSeconds int64,
	pollTimeoutSeconds int64,
) *APIClient {
	return &APIClient{
		baseURL:     strings.TrimRight(baseURL, "/"),
		apiKey:      apiKey,
		bearerToken: bearerToken,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		pollInterval: time.Duration(pollIntervalSeconds) * time.Second,
		pollTimeout:  time.Duration(pollTimeoutSeconds) * time.Second,
	}
}

type taskEnvelope struct {
	Data taskResponse `json:"data"`
}

type taskResponse struct {
	TaskID     string `json:"task_id"`
	Status     string `json:"status"`
	Operation  string `json:"operation"`
	ResourceID string `json:"resource_id"`
	Error      string `json:"error"`
}

type vmCreateRequest struct {
	Name           string            `json:"name"`
	FlavorID       string            `json:"flavor_id"`
	ImageID        string            `json:"image_id"`
	NetworkID      *string           `json:"network_id,omitempty"`
	KeyName        *string           `json:"key_name,omitempty"`
	SecurityGroups []string          `json:"security_groups,omitempty"`
	UserData       *string           `json:"user_data,omitempty"`
	Metadata       map[string]string `json:"metadata,omitempty"`
}

type vmCreateEnvelope struct {
	Data struct {
		TaskID string `json:"task_id"`
	} `json:"data"`
	Meta struct {
		VMID string `json:"vm_id"`
	} `json:"meta"`
}

type vmResponse struct {
	ID             string            `json:"id"`
	Name           string            `json:"name"`
	Status         string            `json:"status"`
	FlavorID       string            `json:"flavor_id"`
	ImageID        string            `json:"image_id"`
	KeyName        string            `json:"key_name"`
	SecurityGroups []string          `json:"security_groups"`
	Metadata       map[string]string `json:"metadata"`
	CreatedAt      string            `json:"created_at"`
	UpdatedAt      string            `json:"updated_at"`
}

type vmGetEnvelope struct {
	Data vmResponse `json:"data"`
}

type taskOnlyEnvelope struct {
	Data struct {
		TaskID string `json:"task_id"`
	} `json:"data"`
}

type vmResizeRequest struct {
	FlavorID string `json:"flavor_id"`
}

type volumeCreateRequest struct {
	Name             string            `json:"name"`
	SizeGB           int64             `json:"size_gb"`
	VolumeType       *string           `json:"volume_type,omitempty"`
	AvailabilityZone *string           `json:"availability_zone,omitempty"`
	Description      *string           `json:"description,omitempty"`
	Metadata         map[string]string `json:"metadata,omitempty"`
}

type volumeCreateEnvelope struct {
	Data struct {
		TaskID string `json:"task_id"`
	} `json:"data"`
	Meta struct {
		VolumeID string `json:"volume_id"`
	} `json:"meta"`
}

type volumeResponse struct {
	ID               string            `json:"id"`
	Name             string            `json:"name"`
	Status           string            `json:"status"`
	SizeGB           int64             `json:"size_gb"`
	VolumeType       string            `json:"volume_type"`
	AvailabilityZone string            `json:"availability_zone"`
	Metadata         map[string]string `json:"metadata"`
	CreatedAt        string            `json:"created_at"`
	UpdatedAt        string            `json:"updated_at"`
}

type volumeGetEnvelope struct {
	Data volumeResponse `json:"data"`
}

type volumeResizeRequest struct {
	NewSizeGB int64 `json:"new_size_gb"`
}

type flavorResponse struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	VCPUs   int64  `json:"vcpus"`
	RAMMB   int64  `json:"ram_mb"`
	DiskGB  int64  `json:"disk_gb"`
	IsPublic bool  `json:"is_public"`
}

type imageResponse struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	Status     string `json:"status"`
	SizeBytes  int64  `json:"size_bytes"`
	MinDiskGB  int64  `json:"min_disk_gb"`
	MinRAMMB   int64  `json:"min_ram_mb"`
	Visibility string `json:"visibility"`
	CreatedAt  string `json:"created_at"`
}

type paginatedFlavorsEnvelope struct {
	Data  []flavorResponse `json:"data"`
	Total int64            `json:"total"`
}

type paginatedImagesEnvelope struct {
	Data  []imageResponse `json:"data"`
	Total int64           `json:"total"`
}

func (c *APIClient) CreateVM(ctx context.Context, req vmCreateRequest) (string, string, error) {
	var out vmCreateEnvelope
	_, err := c.doJSON(ctx, http.MethodPost, "/api/v1/vms", req, &out)
	if err != nil {
		return "", "", err
	}
	if out.Meta.VMID == "" || out.Data.TaskID == "" {
		return "", "", fmt.Errorf("unexpected create VM response")
	}
	return out.Meta.VMID, out.Data.TaskID, nil
}

func (c *APIClient) GetVM(ctx context.Context, vmID string) (vmResponse, error) {
	var out vmGetEnvelope
	_, err := c.doJSON(ctx, http.MethodGet, "/api/v1/vms/"+vmID, nil, &out)
	if err != nil {
		return vmResponse{}, err
	}
	return out.Data, nil
}

func (c *APIClient) DeleteVM(ctx context.Context, vmID string) (string, error) {
	var out taskOnlyEnvelope
	_, err := c.doJSON(ctx, http.MethodDelete, "/api/v1/vms/"+vmID, nil, &out)
	if err != nil {
		return "", err
	}
	return out.Data.TaskID, nil
}

func (c *APIClient) ResizeVM(ctx context.Context, vmID, flavorID string) (string, error) {
	var out taskOnlyEnvelope
	_, err := c.doJSON(
		ctx,
		http.MethodPut,
		"/api/v1/vms/"+vmID+"/resize",
		vmResizeRequest{FlavorID: flavorID},
		&out,
	)
	if err != nil {
		return "", err
	}
	return out.Data.TaskID, nil
}

func (c *APIClient) CreateVolume(ctx context.Context, req volumeCreateRequest) (string, string, error) {
	var out volumeCreateEnvelope
	_, err := c.doJSON(ctx, http.MethodPost, "/api/v1/volumes", req, &out)
	if err != nil {
		return "", "", err
	}
	if out.Meta.VolumeID == "" || out.Data.TaskID == "" {
		return "", "", fmt.Errorf("unexpected create volume response")
	}
	return out.Meta.VolumeID, out.Data.TaskID, nil
}

func (c *APIClient) GetVolume(ctx context.Context, volumeID string) (volumeResponse, error) {
	var out volumeGetEnvelope
	_, err := c.doJSON(ctx, http.MethodGet, "/api/v1/volumes/"+volumeID, nil, &out)
	if err != nil {
		return volumeResponse{}, err
	}
	return out.Data, nil
}

func (c *APIClient) DeleteVolume(ctx context.Context, volumeID string) (string, error) {
	var out taskOnlyEnvelope
	_, err := c.doJSON(ctx, http.MethodDelete, "/api/v1/volumes/"+volumeID, nil, &out)
	if err != nil {
		return "", err
	}
	return out.Data.TaskID, nil
}

func (c *APIClient) ResizeVolume(ctx context.Context, volumeID string, newSizeGB int64) (string, error) {
	var out taskOnlyEnvelope
	_, err := c.doJSON(
		ctx,
		http.MethodPut,
		"/api/v1/volumes/"+volumeID+"/resize",
		volumeResizeRequest{NewSizeGB: newSizeGB},
		&out,
	)
	if err != nil {
		return "", err
	}
	return out.Data.TaskID, nil
}

func (c *APIClient) ListFlavors(ctx context.Context, limit, offset int64) ([]flavorResponse, int64, error) {
	path := "/api/v1/flavors?limit=" + strconv.FormatInt(limit, 10) + "&offset=" + strconv.FormatInt(offset, 10)
	var out paginatedFlavorsEnvelope
	_, err := c.doJSON(ctx, http.MethodGet, path, nil, &out)
	if err != nil {
		return nil, 0, err
	}
	return out.Data, out.Total, nil
}

func (c *APIClient) ListImages(ctx context.Context, limit, offset int64) ([]imageResponse, int64, error) {
	path := "/api/v1/images?limit=" + strconv.FormatInt(limit, 10) + "&offset=" + strconv.FormatInt(offset, 10)
	var out paginatedImagesEnvelope
	_, err := c.doJSON(ctx, http.MethodGet, path, nil, &out)
	if err != nil {
		return nil, 0, err
	}
	return out.Data, out.Total, nil
}

func (c *APIClient) WaitTask(ctx context.Context, taskID string) error {
	deadline := time.Now().Add(c.pollTimeout)

	for {
		if time.Now().After(deadline) {
			return fmt.Errorf("timeout waiting for task %s", taskID)
		}

		var out taskEnvelope
		_, err := c.doJSON(ctx, http.MethodGet, "/api/v1/tasks/"+taskID, nil, &out)
		if err != nil {
			return err
		}

		switch strings.ToLower(out.Data.Status) {
		case "success":
			return nil
		case "failed":
			if out.Data.Error != "" {
				return fmt.Errorf("task failed: %s", out.Data.Error)
			}
			return fmt.Errorf("task failed")
		case "pending", "running":
			// keep polling
		default:
			return fmt.Errorf("unknown task status: %s", out.Data.Status)
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(c.pollInterval):
		}
	}
}

func (c *APIClient) doJSON(ctx context.Context, method, path string, reqBody any, out any) (int, error) {
	fullURL := c.baseURL + path
	if _, err := url.ParseRequestURI(fullURL); err != nil {
		return 0, fmt.Errorf("invalid URL %q: %w", fullURL, err)
	}

	var bodyReader io.Reader
	if reqBody != nil {
		buf := &bytes.Buffer{}
		if err := json.NewEncoder(buf).Encode(reqBody); err != nil {
			return 0, fmt.Errorf("encode request body: %w", err)
		}
		bodyReader = buf
	}

	req, err := http.NewRequestWithContext(ctx, method, fullURL, bodyReader)
	if err != nil {
		return 0, fmt.Errorf("build request: %w", err)
	}

	req.Header.Set("Accept", "application/json")
	if reqBody != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.apiKey != "" {
		req.Header.Set("X-API-Key", c.apiKey)
	}
	if c.bearerToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.bearerToken)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return 0, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return resp.StatusCode, fmt.Errorf("read response body: %w", err)
	}

	if resp.StatusCode == http.StatusNotFound {
		return resp.StatusCode, ErrNotFound
	}

	if resp.StatusCode >= 300 {
		msg := strings.TrimSpace(string(raw))
		if msg == "" {
			msg = http.StatusText(resp.StatusCode)
		}
		return resp.StatusCode, fmt.Errorf("API %s %s failed (%d): %s", method, path, resp.StatusCode, msg)
	}

	if out != nil {
		if err := json.Unmarshal(raw, out); err != nil {
			return resp.StatusCode, fmt.Errorf("decode response body: %w", err)
		}
	}

	return resp.StatusCode, nil
}
